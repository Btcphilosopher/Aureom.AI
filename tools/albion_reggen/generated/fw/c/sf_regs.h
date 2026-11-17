/*
 * sf_regs.h - register definitions and safe accessors
 * GENERATED FILE - DO NOT EDIT.  Edit the register definition instead.
 * generator       : albion_reggen 1.0.0 (definition schema 1)
 * register map    : silicaflux_regs v1.0
 * semantic hash   : 99481283139d2dc0690f688325c0631d115617fc66330be250e7a560f5e43d39
 * definition hash : 322ccd28a62e3936e355677a25425f8609977deab94841f7ce2049bcd96525ba
 */

#ifndef SF_REGS_H
#define SF_REGS_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

#ifdef __cplusplus
#define SF_REGS_STATIC_ASSERT(c, m) static_assert(c, m)
#else
#define SF_REGS_STATIC_ASSERT(c, m) _Static_assert(c, m)
#endif

/* A violated precondition (array index out of range) must never be silent. */
#ifndef SF_REGS_FAULT
#if defined(__GNUC__) || defined(__clang__)
#define SF_REGS_FAULT() __builtin_trap()
#else
#define SF_REGS_FAULT() do { for (;;) { } } while (0)
#endif
#endif

/* Native 64-bit register access is used when pointers are 64 bits wide, unless overridden. */
#ifndef SF_REGS_NATIVE64
#if defined(UINTPTR_MAX) && (UINTPTR_MAX > 0xffffffffu)
#define SF_REGS_NATIVE64 1
#else
#define SF_REGS_NATIVE64 0
#endif
#endif

/*
 * Bus access primitives.  By default registers are accessed with volatile loads and stores
 * through a pointer.  A project that needs a remapped window, a simulator, or a mock can define
 * SF_REGS_CUSTOM_ACCESS and provide these four functions itself:
 *     uint32_t sf_regs_rd32_(uint64_t addr);   void sf_regs_wr32_(uint64_t addr, uint32_t v);
 *     uint64_t sf_regs_rd64n_(uint64_t addr);  void sf_regs_wr64n_(uint64_t addr, uint64_t v);
 * (the *64n_ pair is only called when SF_REGS_NATIVE64 is 1).
 */
#ifndef SF_REGS_CUSTOM_ACCESS
static inline uintptr_t sf_regs_ptr_(uint64_t addr)
{
#if UINTPTR_MAX < UINT64_MAX
    if (addr > (uint64_t)UINTPTR_MAX) {
        SF_REGS_FAULT();   /* the bus address does not fit a pointer: remap via SF_REGS_CUSTOM_ACCESS */
    }
#endif
    return (uintptr_t)addr;
}
static inline uint32_t sf_regs_rd32_(uint64_t addr)
{
    const uintptr_t p = sf_regs_ptr_(addr);
    return *(volatile uint32_t *)p;
}
static inline void sf_regs_wr32_(uint64_t addr, uint32_t v)
{
    const uintptr_t p = sf_regs_ptr_(addr);
    *(volatile uint32_t *)p = v;
}
static inline uint64_t sf_regs_rd64n_(uint64_t addr)
{
    const uintptr_t p = sf_regs_ptr_(addr);
    return *(volatile uint64_t *)p;
}
static inline void sf_regs_wr64n_(uint64_t addr, uint64_t v)
{
    const uintptr_t p = sf_regs_ptr_(addr);
    *(volatile uint64_t *)p = v;
}
#endif

/* 64-bit read of a register whose value can change under us (counters): high-low-high. */
static inline uint64_t sf_regs_rd64_stable_(uint64_t addr)
{
#if SF_REGS_NATIVE64
    return sf_regs_rd64n_(addr);
#else
    uint32_t hi, lo, hi2;
    do {
        hi = sf_regs_rd32_(addr + 4u);
        lo = sf_regs_rd32_(addr);
        hi2 = sf_regs_rd32_(addr + 4u);
    } while (hi != hi2);
    return ((uint64_t)hi << 32) | lo;
#endif
}

/* 64-bit read of any other register: one access if native, else low then high. */
static inline uint64_t sf_regs_rd64_(uint64_t addr)
{
#if SF_REGS_NATIVE64
    return sf_regs_rd64n_(addr);
#else
    uint32_t lo = sf_regs_rd32_(addr);
    uint32_t hi = sf_regs_rd32_(addr + 4u);
    return ((uint64_t)hi << 32) | lo;
#endif
}

/* 64-bit write: one access if native, else low word then high word (two bus transactions). */
static inline void sf_regs_wr64_(uint64_t addr, uint64_t v)
{
#if SF_REGS_NATIVE64
    sf_regs_wr64n_(addr, v);
#else
    sf_regs_wr32_(addr, (uint32_t)v);
    sf_regs_wr32_(addr + 4u, (uint32_t)(v >> 32));
#endif
}

#define SF_REGS_MAP_NAME "silicaflux_regs"
#define SF_REGS_VERSION_MAJOR 1u
#define SF_REGS_VERSION_MINOR 0u
/* equals the value of SYSID.REGMAP_HASH in hardware built from this definition */
#define SF_REGS_MAP_HASH UINT64_C(0x99481283139d2dc0)
#define SF_REGS_SEMANTIC_HASH "99481283139d2dc0690f688325c0631d115617fc66330be250e7a560f5e43d39"
#define SF_REGS_DEFINITION_HASH "322ccd28a62e3936e355677a25425f8609977deab94841f7ce2049bcd96525ba"
#define SF_REGS_NUM_PERIPHERALS 8u
#define SF_REGS_NUM_REGISTERS 193u

/* ===== address map ===== */
#define SF_DMA_BASE UINT64_C(0x120000000)
#define SF_DMA_SIZE UINT64_C(0x1000)
#define SF_TENSOR_BASE UINT64_C(0x150000000)
#define SF_TENSOR_SIZE UINT64_C(0x1000)
#define SF_VECTOR_BASE UINT64_C(0x150001000)
#define SF_VECTOR_SIZE UINT64_C(0x1000)
#define SF_PERF_BASE UINT64_C(0x170000000)
#define SF_PERF_SIZE UINT64_C(0x1000)
#define SF_SYSID_BASE UINT64_C(0x180000000)
#define SF_SYSID_SIZE UINT64_C(0x1000)
#define SF_INTC_BASE UINT64_C(0x180001000)
#define SF_INTC_SIZE UINT64_C(0x1000)
#define SF_CLKRST_BASE UINT64_C(0x180002000)
#define SF_CLKRST_SIZE UINT64_C(0x1000)
#define SF_SRAMC_BASE UINT64_C(0x180003000)
#define SF_SRAMC_SIZE UINT64_C(0x1000)

/* X-macro tables for tools and tests: X(periph, base, size) and X(periph, REG, address, width, reset) */
#define SF_REGS_PERIPH_LIST(X) \
    X(dma, UINT64_C(0x120000000), UINT64_C(0x1000)) \
    X(tensor, UINT64_C(0x150000000), UINT64_C(0x1000)) \
    X(vector, UINT64_C(0x150001000), UINT64_C(0x1000)) \
    X(perf, UINT64_C(0x170000000), UINT64_C(0x1000)) \
    X(sysid, UINT64_C(0x180000000), UINT64_C(0x1000)) \
    X(intc, UINT64_C(0x180001000), UINT64_C(0x1000)) \
    X(clkrst, UINT64_C(0x180002000), UINT64_C(0x1000)) \
    X(sramc, UINT64_C(0x180003000), UINT64_C(0x1000)) \
    /* end */
#define SF_REGS_REG_LIST(X) \
    X(dma, SRC, UINT64_C(0x120000000), 32, UINT32_C(0x0)) \
    X(dma, DST, UINT64_C(0x120000004), 32, UINT32_C(0x0)) \
    X(dma, LEN, UINT64_C(0x120000008), 32, UINT32_C(0x0)) \
    X(dma, TAG, UINT64_C(0x12000000c), 32, UINT32_C(0x0)) \
    X(dma, CTRL, UINT64_C(0x120000010), 32, UINT32_C(0x0)) \
    X(dma, START, UINT64_C(0x120000014), 32, UINT32_C(0x0)) \
    X(dma, STATUS, UINT64_C(0x120000018), 32, UINT32_C(0x0)) \
    X(dma, BYTES_DONE, UINT64_C(0x12000001c), 32, UINT32_C(0x0)) \
    X(dma, CPL_STATUS, UINT64_C(0x120000020), 32, UINT32_C(0x0)) \
    X(dma, CPL_ERR_ADDR, UINT64_C(0x120000024), 32, UINT32_C(0x0)) \
    X(dma, CPL_BYTES, UINT64_C(0x120000028), 32, UINT32_C(0x0)) \
    X(dma, CPL_POP, UINT64_C(0x12000002c), 32, UINT32_C(0x0)) \
    X(dma, PERF_CTRL, UINT64_C(0x120000030), 32, UINT32_C(0x0)) \
    X(dma, INT_ENABLE, UINT64_C(0x120000034), 32, UINT32_C(0x0)) \
    X(dma, INT_STATUS, UINT64_C(0x120000038), 32, UINT32_C(0x0)) \
    X(dma, PERF_0, UINT64_C(0x120000040), 32, UINT32_C(0x0)) \
    X(dma, PERF_1, UINT64_C(0x120000044), 32, UINT32_C(0x0)) \
    X(dma, PERF_2, UINT64_C(0x120000048), 32, UINT32_C(0x0)) \
    X(dma, PERF_3, UINT64_C(0x12000004c), 32, UINT32_C(0x0)) \
    X(dma, PERF_4, UINT64_C(0x120000050), 32, UINT32_C(0x0)) \
    X(dma, PERF_5, UINT64_C(0x120000054), 32, UINT32_C(0x0)) \
    X(dma, PERF_6, UINT64_C(0x120000058), 32, UINT32_C(0x0)) \
    X(dma, PERF_7, UINT64_C(0x12000005c), 32, UINT32_C(0x0)) \
    X(dma, PERF_8, UINT64_C(0x120000060), 32, UINT32_C(0x0)) \
    X(dma, PERF_9, UINT64_C(0x120000064), 32, UINT32_C(0x0)) \
    X(dma, PERF_10, UINT64_C(0x120000068), 32, UINT32_C(0x0)) \
    X(dma, PERF_11, UINT64_C(0x12000006c), 32, UINT32_C(0x0)) \
    X(dma, PERF_12, UINT64_C(0x120000070), 32, UINT32_C(0x0)) \
    X(dma, PERF_13, UINT64_C(0x120000074), 32, UINT32_C(0x0)) \
    X(dma, PERF_14, UINT64_C(0x120000078), 32, UINT32_C(0x0)) \
    X(dma, PERF_15, UINT64_C(0x12000007c), 32, UINT32_C(0x0)) \
    X(tensor, ID, UINT64_C(0x150000000), 32, UINT32_C(0x53465443)) \
    X(tensor, INFO, UINT64_C(0x150000004), 32, UINT32_C(0x0)) \
    X(tensor, CAPS, UINT64_C(0x150000008), 32, UINT32_C(0x0)) \
    X(tensor, OPBUF, UINT64_C(0x15000000c), 32, UINT32_C(0x0)) \
    X(tensor, MEM_LO, UINT64_C(0x150000010), 32, UINT32_C(0x0)) \
    X(tensor, MEM_LAST, UINT64_C(0x150000014), 32, UINT32_C(0x0)) \
    X(tensor, CTRL, UINT64_C(0x150000018), 32, UINT32_C(0x0)) \
    X(tensor, STATUS, UINT64_C(0x15000001c), 32, UINT32_C(0x0)) \
    X(tensor, INT_ENABLE, UINT64_C(0x150000020), 32, UINT32_C(0x0)) \
    X(tensor, INT_STATUS, UINT64_C(0x150000024), 32, UINT32_C(0x0)) \
    X(tensor, SUBMITTED, UINT64_C(0x150000028), 32, UINT32_C(0x0)) \
    X(tensor, KMAX, UINT64_C(0x15000002c), 32, UINT32_C(0x0)) \
    X(tensor, DESC_0, UINT64_C(0x150000040), 32, UINT32_C(0x0)) \
    X(tensor, DESC_1, UINT64_C(0x150000044), 32, UINT32_C(0x0)) \
    X(tensor, DESC_2, UINT64_C(0x150000048), 32, UINT32_C(0x0)) \
    X(tensor, DESC_3, UINT64_C(0x15000004c), 32, UINT32_C(0x0)) \
    X(tensor, DESC_4, UINT64_C(0x150000050), 32, UINT32_C(0x0)) \
    X(tensor, DESC_5, UINT64_C(0x150000054), 32, UINT32_C(0x0)) \
    X(tensor, DESC_6, UINT64_C(0x150000058), 32, UINT32_C(0x0)) \
    X(tensor, DESC_7, UINT64_C(0x15000005c), 32, UINT32_C(0x0)) \
    X(tensor, DESC_8, UINT64_C(0x150000060), 32, UINT32_C(0x0)) \
    X(tensor, DESC_9, UINT64_C(0x150000064), 32, UINT32_C(0x0)) \
    X(tensor, DESC_10, UINT64_C(0x150000068), 32, UINT32_C(0x0)) \
    X(tensor, DESC_11, UINT64_C(0x15000006c), 32, UINT32_C(0x0)) \
    X(tensor, DOORBELL, UINT64_C(0x150000070), 32, UINT32_C(0x0)) \
    X(tensor, CPL_0, UINT64_C(0x150000080), 32, UINT32_C(0x0)) \
    X(tensor, CPL_1, UINT64_C(0x150000084), 32, UINT32_C(0x0)) \
    X(tensor, CPL_2, UINT64_C(0x150000088), 32, UINT32_C(0x0)) \
    X(tensor, CPL_3, UINT64_C(0x15000008c), 32, UINT32_C(0x0)) \
    X(tensor, CPL_4, UINT64_C(0x150000090), 32, UINT32_C(0x0)) \
    X(tensor, CPL_5, UINT64_C(0x150000094), 32, UINT32_C(0x0)) \
    X(tensor, CPL_POP, UINT64_C(0x150000098), 32, UINT32_C(0x0)) \
    X(tensor, PERF_0, UINT64_C(0x150000100), 32, UINT32_C(0x0)) \
    X(tensor, PERF_1, UINT64_C(0x150000104), 32, UINT32_C(0x0)) \
    X(tensor, PERF_2, UINT64_C(0x150000108), 32, UINT32_C(0x0)) \
    X(tensor, PERF_3, UINT64_C(0x15000010c), 32, UINT32_C(0x0)) \
    X(tensor, PERF_4, UINT64_C(0x150000110), 32, UINT32_C(0x0)) \
    X(tensor, PERF_5, UINT64_C(0x150000114), 32, UINT32_C(0x0)) \
    X(tensor, PERF_6, UINT64_C(0x150000118), 32, UINT32_C(0x0)) \
    X(tensor, PERF_7, UINT64_C(0x15000011c), 32, UINT32_C(0x0)) \
    X(tensor, PERF_8, UINT64_C(0x150000120), 32, UINT32_C(0x0)) \
    X(tensor, PERF_9, UINT64_C(0x150000124), 32, UINT32_C(0x0)) \
    X(tensor, PERF_10, UINT64_C(0x150000128), 32, UINT32_C(0x0)) \
    X(tensor, PERF_11, UINT64_C(0x15000012c), 32, UINT32_C(0x0)) \
    X(tensor, PERF_12, UINT64_C(0x150000130), 32, UINT32_C(0x0)) \
    X(tensor, PERF_13, UINT64_C(0x150000134), 32, UINT32_C(0x0)) \
    X(tensor, PERF_14, UINT64_C(0x150000138), 32, UINT32_C(0x0)) \
    X(tensor, PERF_15, UINT64_C(0x15000013c), 32, UINT32_C(0x0)) \
    X(tensor, PERF_16, UINT64_C(0x150000140), 32, UINT32_C(0x0)) \
    X(tensor, PERF_17, UINT64_C(0x150000144), 32, UINT32_C(0x0)) \
    X(tensor, PERF_18, UINT64_C(0x150000148), 32, UINT32_C(0x0)) \
    X(tensor, PERF_19, UINT64_C(0x15000014c), 32, UINT32_C(0x0)) \
    X(tensor, DMA_PERF_0, UINT64_C(0x150000200), 32, UINT32_C(0x0)) \
    X(tensor, DMA_PERF_1, UINT64_C(0x150000204), 32, UINT32_C(0x0)) \
    X(tensor, DMA_PERF_2, UINT64_C(0x150000208), 32, UINT32_C(0x0)) \
    X(tensor, DMA_PERF_3, UINT64_C(0x15000020c), 32, UINT32_C(0x0)) \
    X(tensor, DMA_PERF_4, UINT64_C(0x150000210), 32, UINT32_C(0x0)) \
    X(tensor, DMA_PERF_5, UINT64_C(0x150000214), 32, UINT32_C(0x0)) \
    X(tensor, DMA_PERF_6, UINT64_C(0x150000218), 32, UINT32_C(0x0)) \
    X(tensor, DMA_PERF_7, UINT64_C(0x15000021c), 32, UINT32_C(0x0)) \
    X(tensor, DMA_PERF_8, UINT64_C(0x150000220), 32, UINT32_C(0x0)) \
    X(tensor, DMA_PERF_9, UINT64_C(0x150000224), 32, UINT32_C(0x0)) \
    X(tensor, DMA_PERF_10, UINT64_C(0x150000228), 32, UINT32_C(0x0)) \
    X(tensor, DMA_PERF_11, UINT64_C(0x15000022c), 32, UINT32_C(0x0)) \
    X(tensor, DMA_PERF_12, UINT64_C(0x150000230), 32, UINT32_C(0x0)) \
    X(tensor, DMA_PERF_13, UINT64_C(0x150000234), 32, UINT32_C(0x0)) \
    X(tensor, DMA_PERF_14, UINT64_C(0x150000238), 32, UINT32_C(0x0)) \
    X(tensor, DMA_PERF_15, UINT64_C(0x15000023c), 32, UINT32_C(0x0)) \
    X(tensor, DMA_PERF_16, UINT64_C(0x150000240), 32, UINT32_C(0x0)) \
    X(tensor, DMA_PERF_17, UINT64_C(0x150000244), 32, UINT32_C(0x0)) \
    X(vector, ID, UINT64_C(0x150001000), 32, UINT32_C(0x53464351)) \
    X(vector, INFO, UINT64_C(0x150001004), 32, UINT32_C(0x0)) \
    X(vector, CTRL, UINT64_C(0x150001008), 32, UINT32_C(0x0)) \
    X(vector, STATUS, UINT64_C(0x15000100c), 32, UINT32_C(0x0)) \
    X(vector, INT_ENABLE, UINT64_C(0x150001010), 32, UINT32_C(0x0)) \
    X(vector, INT_STATUS, UINT64_C(0x150001014), 32, UINT32_C(0x0)) \
    X(vector, SUBMITTED, UINT64_C(0x150001018), 32, UINT32_C(0x0)) \
    X(vector, DESC_0, UINT64_C(0x150001020), 32, UINT32_C(0x0)) \
    X(vector, DESC_1, UINT64_C(0x150001024), 32, UINT32_C(0x0)) \
    X(vector, DESC_2, UINT64_C(0x150001028), 32, UINT32_C(0x0)) \
    X(vector, DESC_3, UINT64_C(0x15000102c), 32, UINT32_C(0x0)) \
    X(vector, DESC_4, UINT64_C(0x150001030), 32, UINT32_C(0x0)) \
    X(vector, DESC_5, UINT64_C(0x150001034), 32, UINT32_C(0x0)) \
    X(vector, DESC_6, UINT64_C(0x150001038), 32, UINT32_C(0x0)) \
    X(vector, DESC_7, UINT64_C(0x15000103c), 32, UINT32_C(0x0)) \
    X(vector, DOORBELL, UINT64_C(0x150001040), 32, UINT32_C(0x0)) \
    X(vector, CPL_0, UINT64_C(0x150001050), 32, UINT32_C(0x0)) \
    X(vector, CPL_1, UINT64_C(0x150001054), 32, UINT32_C(0x0)) \
    X(vector, CPL_2, UINT64_C(0x150001058), 32, UINT32_C(0x0)) \
    X(vector, CPL_3, UINT64_C(0x15000105c), 32, UINT32_C(0x0)) \
    X(vector, CPL_POP, UINT64_C(0x150001060), 32, UINT32_C(0x0)) \
    X(vector, PERF_0, UINT64_C(0x150001080), 32, UINT32_C(0x0)) \
    X(vector, PERF_1, UINT64_C(0x150001084), 32, UINT32_C(0x0)) \
    X(vector, PERF_2, UINT64_C(0x150001088), 32, UINT32_C(0x0)) \
    X(vector, PERF_3, UINT64_C(0x15000108c), 32, UINT32_C(0x0)) \
    X(vector, PERF_4, UINT64_C(0x150001090), 32, UINT32_C(0x0)) \
    X(vector, PERF_5, UINT64_C(0x150001094), 32, UINT32_C(0x0)) \
    X(vector, PERF_6, UINT64_C(0x150001098), 32, UINT32_C(0x0)) \
    X(vector, PERF_7, UINT64_C(0x15000109c), 32, UINT32_C(0x0)) \
    X(vector, PERF_8, UINT64_C(0x1500010a0), 32, UINT32_C(0x0)) \
    X(vector, PERF_9, UINT64_C(0x1500010a4), 32, UINT32_C(0x0)) \
    X(vector, PERF_10, UINT64_C(0x1500010a8), 32, UINT32_C(0x0)) \
    X(vector, PERF_11, UINT64_C(0x1500010ac), 32, UINT32_C(0x0)) \
    X(vector, PERF_12, UINT64_C(0x1500010b0), 32, UINT32_C(0x0)) \
    X(vector, PERF_13, UINT64_C(0x1500010b4), 32, UINT32_C(0x0)) \
    X(vector, PERF_14, UINT64_C(0x1500010b8), 32, UINT32_C(0x0)) \
    X(vector, PERF_15, UINT64_C(0x1500010bc), 32, UINT32_C(0x0)) \
    X(vector, PERF_16, UINT64_C(0x1500010c0), 32, UINT32_C(0x0)) \
    X(perf, CTRL, UINT64_C(0x170000000), 32, UINT32_C(0x0)) \
    X(perf, STATUS, UINT64_C(0x170000004), 32, UINT32_C(0x0)) \
    X(perf, CNT_0, UINT64_C(0x170000100), 64, UINT64_C(0x0)) \
    X(perf, CNT_1, UINT64_C(0x170000108), 64, UINT64_C(0x0)) \
    X(perf, CNT_2, UINT64_C(0x170000110), 64, UINT64_C(0x0)) \
    X(perf, CNT_3, UINT64_C(0x170000118), 64, UINT64_C(0x0)) \
    X(perf, CNT_4, UINT64_C(0x170000120), 64, UINT64_C(0x0)) \
    X(perf, CNT_5, UINT64_C(0x170000128), 64, UINT64_C(0x0)) \
    X(perf, CNT_6, UINT64_C(0x170000130), 64, UINT64_C(0x0)) \
    X(perf, CNT_7, UINT64_C(0x170000138), 64, UINT64_C(0x0)) \
    X(perf, CNT_8, UINT64_C(0x170000140), 64, UINT64_C(0x0)) \
    X(perf, CNT_9, UINT64_C(0x170000148), 64, UINT64_C(0x0)) \
    X(perf, CNT_10, UINT64_C(0x170000150), 64, UINT64_C(0x0)) \
    X(perf, CNT_11, UINT64_C(0x170000158), 64, UINT64_C(0x0)) \
    X(perf, CNT_12, UINT64_C(0x170000160), 64, UINT64_C(0x0)) \
    X(perf, CNT_13, UINT64_C(0x170000168), 64, UINT64_C(0x0)) \
    X(perf, CNT_14, UINT64_C(0x170000170), 64, UINT64_C(0x0)) \
    X(perf, CNT_15, UINT64_C(0x170000178), 64, UINT64_C(0x0)) \
    X(perf, CNT_16, UINT64_C(0x170000180), 64, UINT64_C(0x0)) \
    X(perf, CNT_17, UINT64_C(0x170000188), 64, UINT64_C(0x0)) \
    X(perf, CNT_18, UINT64_C(0x170000190), 64, UINT64_C(0x0)) \
    X(perf, CNT_19, UINT64_C(0x170000198), 64, UINT64_C(0x0)) \
    X(perf, CNT_20, UINT64_C(0x1700001a0), 64, UINT64_C(0x0)) \
    X(perf, CNT_21, UINT64_C(0x1700001a8), 64, UINT64_C(0x0)) \
    X(perf, CNT_22, UINT64_C(0x1700001b0), 64, UINT64_C(0x0)) \
    X(sysid, ID, UINT64_C(0x180000000), 32, UINT32_C(0x53464c58)) \
    X(sysid, REGMAP_VERSION, UINT64_C(0x180000004), 32, UINT32_C(0x10000)) \
    X(sysid, ALP_VERSION, UINT64_C(0x180000008), 32, UINT32_C(0x1)) \
    X(sysid, LIB_VERSION, UINT64_C(0x18000000c), 32, UINT32_C(0x100)) \
    X(sysid, ALP_CAPS, UINT64_C(0x180000010), 64, UINT64_C(0x1040488000020003)) \
    X(sysid, REGMAP_HASH, UINT64_C(0x180000018), 64, UINT64_C(0x99481283139d2dc0)) \
    X(sysid, BUILD_ID, UINT64_C(0x180000020), 32, UINT32_C(0x0)) \
    X(intc, PENDING, UINT64_C(0x180001000), 32, UINT32_C(0x0)) \
    X(intc, ENABLE, UINT64_C(0x180001004), 32, UINT32_C(0x0)) \
    X(intc, CLAIM, UINT64_C(0x180001008), 32, UINT32_C(0x0)) \
    X(intc, SWPEND, UINT64_C(0x18000100c), 32, UINT32_C(0x0)) \
    X(intc, THRESHOLD, UINT64_C(0x180001010), 32, UINT32_C(0x0)) \
    X(intc, ACTIVE, UINT64_C(0x180001014), 32, UINT32_C(0x0)) \
    X(intc, PRIO0, UINT64_C(0x180001020), 32, UINT32_C(0x11111111)) \
    X(intc, PRIO1, UINT64_C(0x180001024), 32, UINT32_C(0x11111111)) \
    X(clkrst, ID, UINT64_C(0x180002000), 32, UINT32_C(0x53464354)) \
    X(clkrst, CONFIG, UINT64_C(0x180002004), 32, UINT32_C(0x0)) \
    X(clkrst, STATUS, UINT64_C(0x180002008), 32, UINT32_C(0x0)) \
    X(clkrst, CAUSE, UINT64_C(0x18000200c), 32, UINT32_C(0x0)) \
    X(clkrst, RST_INFO, UINT64_C(0x180002010), 32, UINT32_C(0x0)) \
    X(clkrst, CLK_EN, UINT64_C(0x180002018), 32, UINT32_C(0xff)) \
    X(clkrst, CLK_STAT, UINT64_C(0x18000201c), 32, UINT32_C(0x0)) \
    X(clkrst, WDOG_CNT, UINT64_C(0x18000202c), 32, UINT32_C(0x0)) \
    X(clkrst, CLK_MEAS, UINT64_C(0x180002030), 32, UINT32_C(0x0)) \
    X(clkrst, IRQ, UINT64_C(0x180002034), 32, UINT32_C(0x0)) \
    X(sramc, CTRL, UINT64_C(0x180003000), 32, UINT32_C(0xf)) \
    X(sramc, STATUS, UINT64_C(0x180003008), 32, UINT32_C(0x0)) \
    X(sramc, PERF_CTRL, UINT64_C(0x180003010), 32, UINT32_C(0x0)) \
    X(sramc, PERF_VAL, UINT64_C(0x180003014), 32, UINT32_C(0x0)) \
    /* end */

/* ===== registers ===== */

/* ---------- dma: DMA controller (descriptor, completion, status, interrupts, counters) ---------- */
/* region dma; window 0x120000000 + 0x1000 ; privileged access only */

/* dma.SRC: 32-bit @ offset 0x0 - Descriptor source address (bytes) */
#define SF_DMA_SRC_OFFSET UINT64_C(0x0)
#define SF_DMA_SRC_ADDR UINT64_C(0x120000000)
#define SF_DMA_SRC_WIDTH 32u
#define SF_DMA_SRC_RESET UINT32_C(0x0)
#define SF_DMA_SRC_RW_MASK UINT32_C(0xffffffff)
SF_REGS_STATIC_ASSERT((SF_DMA_SRC_ADDR % 4u) == 0u, "dma.SRC is not naturally aligned");
#define SF_DMA_SRC_VALUE_SHIFT 0u
#define SF_DMA_SRC_VALUE_WIDTH 32u
#define SF_DMA_SRC_VALUE_MASK UINT32_C(0xffffffff)
#define SF_DMA_SRC_VALUE_RESET UINT32_C(0x0)
static inline uint32_t sf_dma_src_read(void)
{
    return sf_regs_rd32_(SF_DMA_SRC_ADDR);
}
static inline void sf_dma_src_write(uint32_t value)
{
    sf_regs_wr32_(SF_DMA_SRC_ADDR, value);
}
static inline uint32_t sf_dma_src_get_value(uint32_t reg)
{
    return (reg & SF_DMA_SRC_VALUE_MASK) >> SF_DMA_SRC_VALUE_SHIFT;
}
static inline uint32_t sf_dma_src_value_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_DMA_SRC_VALUE_SHIFT) & SF_DMA_SRC_VALUE_MASK;
}
/* RMW of rw field VALUE: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_dma_src_set_value(uint32_t value)
{
    uint32_t v = sf_dma_src_read() & SF_DMA_SRC_RW_MASK;
    v = (v & ~SF_DMA_SRC_VALUE_MASK) | sf_dma_src_value_encode(value);
    sf_dma_src_write(v);
}

/* dma.DST: 32-bit @ offset 0x4 - Descriptor destination address (bytes) */
#define SF_DMA_DST_OFFSET UINT64_C(0x4)
#define SF_DMA_DST_ADDR UINT64_C(0x120000004)
#define SF_DMA_DST_WIDTH 32u
#define SF_DMA_DST_RESET UINT32_C(0x0)
#define SF_DMA_DST_RW_MASK UINT32_C(0xffffffff)
SF_REGS_STATIC_ASSERT((SF_DMA_DST_ADDR % 4u) == 0u, "dma.DST is not naturally aligned");
#define SF_DMA_DST_VALUE_SHIFT 0u
#define SF_DMA_DST_VALUE_WIDTH 32u
#define SF_DMA_DST_VALUE_MASK UINT32_C(0xffffffff)
#define SF_DMA_DST_VALUE_RESET UINT32_C(0x0)
static inline uint32_t sf_dma_dst_read(void)
{
    return sf_regs_rd32_(SF_DMA_DST_ADDR);
}
static inline void sf_dma_dst_write(uint32_t value)
{
    sf_regs_wr32_(SF_DMA_DST_ADDR, value);
}
static inline uint32_t sf_dma_dst_get_value(uint32_t reg)
{
    return (reg & SF_DMA_DST_VALUE_MASK) >> SF_DMA_DST_VALUE_SHIFT;
}
static inline uint32_t sf_dma_dst_value_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_DMA_DST_VALUE_SHIFT) & SF_DMA_DST_VALUE_MASK;
}
/* RMW of rw field VALUE: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_dma_dst_set_value(uint32_t value)
{
    uint32_t v = sf_dma_dst_read() & SF_DMA_DST_RW_MASK;
    v = (v & ~SF_DMA_DST_VALUE_MASK) | sf_dma_dst_value_encode(value);
    sf_dma_dst_write(v);
}

/* dma.LEN: 32-bit @ offset 0x8 - Descriptor length in bytes */
#define SF_DMA_LEN_OFFSET UINT64_C(0x8)
#define SF_DMA_LEN_ADDR UINT64_C(0x120000008)
#define SF_DMA_LEN_WIDTH 32u
#define SF_DMA_LEN_RESET UINT32_C(0x0)
#define SF_DMA_LEN_RW_MASK UINT32_C(0xffffffff)
SF_REGS_STATIC_ASSERT((SF_DMA_LEN_ADDR % 4u) == 0u, "dma.LEN is not naturally aligned");
#define SF_DMA_LEN_VALUE_SHIFT 0u
#define SF_DMA_LEN_VALUE_WIDTH 32u
#define SF_DMA_LEN_VALUE_MASK UINT32_C(0xffffffff)
#define SF_DMA_LEN_VALUE_RESET UINT32_C(0x0)
static inline uint32_t sf_dma_len_read(void)
{
    return sf_regs_rd32_(SF_DMA_LEN_ADDR);
}
static inline void sf_dma_len_write(uint32_t value)
{
    sf_regs_wr32_(SF_DMA_LEN_ADDR, value);
}
static inline uint32_t sf_dma_len_get_value(uint32_t reg)
{
    return (reg & SF_DMA_LEN_VALUE_MASK) >> SF_DMA_LEN_VALUE_SHIFT;
}
static inline uint32_t sf_dma_len_value_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_DMA_LEN_VALUE_SHIFT) & SF_DMA_LEN_VALUE_MASK;
}
/* RMW of rw field VALUE: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_dma_len_set_value(uint32_t value)
{
    uint32_t v = sf_dma_len_read() & SF_DMA_LEN_RW_MASK;
    v = (v & ~SF_DMA_LEN_VALUE_MASK) | sf_dma_len_value_encode(value);
    sf_dma_len_write(v);
}

/* dma.TAG: 32-bit @ offset 0xc - Descriptor tag, echoed in the completion record */
#define SF_DMA_TAG_OFFSET UINT64_C(0xc)
#define SF_DMA_TAG_ADDR UINT64_C(0x12000000c)
#define SF_DMA_TAG_WIDTH 32u
#define SF_DMA_TAG_RESET UINT32_C(0x0)
#define SF_DMA_TAG_RW_MASK UINT32_C(0xff)
SF_REGS_STATIC_ASSERT((SF_DMA_TAG_ADDR % 4u) == 0u, "dma.TAG is not naturally aligned");
#define SF_DMA_TAG_TAG_SHIFT 0u
#define SF_DMA_TAG_TAG_WIDTH 8u
#define SF_DMA_TAG_TAG_MASK UINT32_C(0xff)
#define SF_DMA_TAG_TAG_RESET UINT32_C(0x0)
static inline uint32_t sf_dma_tag_read(void)
{
    return sf_regs_rd32_(SF_DMA_TAG_ADDR);
}
static inline void sf_dma_tag_write(uint32_t value)
{
    sf_regs_wr32_(SF_DMA_TAG_ADDR, value);
}
static inline uint32_t sf_dma_tag_get_tag(uint32_t reg)
{
    return (reg & SF_DMA_TAG_TAG_MASK) >> SF_DMA_TAG_TAG_SHIFT;
}
static inline uint32_t sf_dma_tag_tag_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_DMA_TAG_TAG_SHIFT) & SF_DMA_TAG_TAG_MASK;
}
/* RMW of rw field TAG: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_dma_tag_set_tag(uint32_t value)
{
    uint32_t v = sf_dma_tag_read() & SF_DMA_TAG_RW_MASK;
    v = (v & ~SF_DMA_TAG_TAG_MASK) | sf_dma_tag_tag_encode(value);
    sf_dma_tag_write(v);
}

/* dma.CTRL: 32-bit @ offset 0x10 - Transfer control */
#define SF_DMA_CTRL_OFFSET UINT64_C(0x10)
#define SF_DMA_CTRL_ADDR UINT64_C(0x120000010)
#define SF_DMA_CTRL_WIDTH 32u
#define SF_DMA_CTRL_RESET UINT32_C(0x0)
#define SF_DMA_CTRL_RW_MASK UINT32_C(0x1)
SF_REGS_STATIC_ASSERT((SF_DMA_CTRL_ADDR % 4u) == 0u, "dma.CTRL is not naturally aligned");
#define SF_DMA_CTRL_ABORT_SHIFT 0u
#define SF_DMA_CTRL_ABORT_WIDTH 1u
#define SF_DMA_CTRL_ABORT_MASK UINT32_C(0x1)
#define SF_DMA_CTRL_ABORT_RESET UINT32_C(0x0)
static inline uint32_t sf_dma_ctrl_read(void)
{
    return sf_regs_rd32_(SF_DMA_CTRL_ADDR);
}
static inline void sf_dma_ctrl_write(uint32_t value)
{
    sf_regs_wr32_(SF_DMA_CTRL_ADDR, value);
}
static inline uint32_t sf_dma_ctrl_get_abort(uint32_t reg)
{
    return (reg & SF_DMA_CTRL_ABORT_MASK) >> SF_DMA_CTRL_ABORT_SHIFT;
}
static inline uint32_t sf_dma_ctrl_abort_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_DMA_CTRL_ABORT_SHIFT) & SF_DMA_CTRL_ABORT_MASK;
}
/* RMW of rw field ABORT: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_dma_ctrl_set_abort(uint32_t value)
{
    uint32_t v = sf_dma_ctrl_read() & SF_DMA_CTRL_RW_MASK;
    v = (v & ~SF_DMA_CTRL_ABORT_MASK) | sf_dma_ctrl_abort_encode(value);
    sf_dma_ctrl_write(v);
}

/* dma.START: 32-bit @ offset 0x14 - Submit the staged descriptor. Refused (TARGET_ERR) while the descriptor queue is full. */
#define SF_DMA_START_OFFSET UINT64_C(0x14)
#define SF_DMA_START_ADDR UINT64_C(0x120000014)
#define SF_DMA_START_WIDTH 32u
#define SF_DMA_START_RESET UINT32_C(0x0)
#define SF_DMA_START_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_DMA_START_ADDR % 4u) == 0u, "dma.START is not naturally aligned");
#define SF_DMA_START_GO_SHIFT 0u
#define SF_DMA_START_GO_WIDTH 32u
#define SF_DMA_START_GO_MASK UINT32_C(0xffffffff)
#define SF_DMA_START_GO_RESET UINT32_C(0x0)
static inline void sf_dma_start_write(uint32_t value)
{
    sf_regs_wr32_(SF_DMA_START_ADDR, value);
}
static inline uint32_t sf_dma_start_go_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_DMA_START_GO_SHIFT) & SF_DMA_START_GO_MASK;
}

/* dma.STATUS: 32-bit @ offset 0x18 - Engine status */
#define SF_DMA_STATUS_OFFSET UINT64_C(0x18)
#define SF_DMA_STATUS_ADDR UINT64_C(0x120000018)
#define SF_DMA_STATUS_WIDTH 32u
#define SF_DMA_STATUS_RESET UINT32_C(0x0)
#define SF_DMA_STATUS_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_DMA_STATUS_ADDR % 4u) == 0u, "dma.STATUS is not naturally aligned");
#define SF_DMA_STATUS_BUSY_SHIFT 0u
#define SF_DMA_STATUS_BUSY_WIDTH 1u
#define SF_DMA_STATUS_BUSY_MASK UINT32_C(0x1)
#define SF_DMA_STATUS_BUSY_RESET UINT32_C(0x0)
#define SF_DMA_STATUS_ACTIVE_SHIFT 1u
#define SF_DMA_STATUS_ACTIVE_WIDTH 1u
#define SF_DMA_STATUS_ACTIVE_MASK UINT32_C(0x2)
#define SF_DMA_STATUS_ACTIVE_RESET UINT32_C(0x0)
#define SF_DMA_STATUS_CTL_STATE_SHIFT 2u
#define SF_DMA_STATUS_CTL_STATE_WIDTH 2u
#define SF_DMA_STATUS_CTL_STATE_MASK UINT32_C(0xc)
#define SF_DMA_STATUS_CTL_STATE_RESET UINT32_C(0x0)
#define SF_DMA_STATUS_ENG_STATE_SHIFT 4u
#define SF_DMA_STATUS_ENG_STATE_WIDTH 3u
#define SF_DMA_STATUS_ENG_STATE_MASK UINT32_C(0x70)
#define SF_DMA_STATUS_ENG_STATE_RESET UINT32_C(0x0)
#define SF_DMA_STATUS_CUR_TAG_SHIFT 8u
#define SF_DMA_STATUS_CUR_TAG_WIDTH 8u
#define SF_DMA_STATUS_CUR_TAG_MASK UINT32_C(0xff00)
#define SF_DMA_STATUS_CUR_TAG_RESET UINT32_C(0x0)
#define SF_DMA_STATUS_FIFO_LEVEL_SHIFT 16u
#define SF_DMA_STATUS_FIFO_LEVEL_WIDTH 8u
#define SF_DMA_STATUS_FIFO_LEVEL_MASK UINT32_C(0xff0000)
#define SF_DMA_STATUS_FIFO_LEVEL_RESET UINT32_C(0x0)
static inline uint32_t sf_dma_status_read(void)
{
    return sf_regs_rd32_(SF_DMA_STATUS_ADDR);
}
static inline uint32_t sf_dma_status_get_busy(uint32_t reg)
{
    return (reg & SF_DMA_STATUS_BUSY_MASK) >> SF_DMA_STATUS_BUSY_SHIFT;
}
static inline uint32_t sf_dma_status_get_active(uint32_t reg)
{
    return (reg & SF_DMA_STATUS_ACTIVE_MASK) >> SF_DMA_STATUS_ACTIVE_SHIFT;
}
static inline uint32_t sf_dma_status_get_ctl_state(uint32_t reg)
{
    return (reg & SF_DMA_STATUS_CTL_STATE_MASK) >> SF_DMA_STATUS_CTL_STATE_SHIFT;
}
static inline uint32_t sf_dma_status_get_eng_state(uint32_t reg)
{
    return (reg & SF_DMA_STATUS_ENG_STATE_MASK) >> SF_DMA_STATUS_ENG_STATE_SHIFT;
}
static inline uint32_t sf_dma_status_get_cur_tag(uint32_t reg)
{
    return (reg & SF_DMA_STATUS_CUR_TAG_MASK) >> SF_DMA_STATUS_CUR_TAG_SHIFT;
}
static inline uint32_t sf_dma_status_get_fifo_level(uint32_t reg)
{
    return (reg & SF_DMA_STATUS_FIFO_LEVEL_MASK) >> SF_DMA_STATUS_FIFO_LEVEL_SHIFT;
}

/* dma.BYTES_DONE: 32-bit @ offset 0x1c - Bytes acknowledged so far by the transfer in progress */
#define SF_DMA_BYTES_DONE_OFFSET UINT64_C(0x1c)
#define SF_DMA_BYTES_DONE_ADDR UINT64_C(0x12000001c)
#define SF_DMA_BYTES_DONE_WIDTH 32u
#define SF_DMA_BYTES_DONE_RESET UINT32_C(0x0)
#define SF_DMA_BYTES_DONE_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_DMA_BYTES_DONE_ADDR % 4u) == 0u, "dma.BYTES_DONE is not naturally aligned");
#define SF_DMA_BYTES_DONE_VALUE_SHIFT 0u
#define SF_DMA_BYTES_DONE_VALUE_WIDTH 32u
#define SF_DMA_BYTES_DONE_VALUE_MASK UINT32_C(0xffffffff)
#define SF_DMA_BYTES_DONE_VALUE_RESET UINT32_C(0x0)
static inline uint32_t sf_dma_bytes_done_read(void)
{
    return sf_regs_rd32_(SF_DMA_BYTES_DONE_ADDR);
}
static inline uint32_t sf_dma_bytes_done_get_value(uint32_t reg)
{
    return (reg & SF_DMA_BYTES_DONE_VALUE_MASK) >> SF_DMA_BYTES_DONE_VALUE_SHIFT;
}

/* dma.CPL_STATUS: 32-bit @ offset 0x20 - Head completion record */
#define SF_DMA_CPL_STATUS_OFFSET UINT64_C(0x20)
#define SF_DMA_CPL_STATUS_ADDR UINT64_C(0x120000020)
#define SF_DMA_CPL_STATUS_WIDTH 32u
#define SF_DMA_CPL_STATUS_RESET UINT32_C(0x0)
#define SF_DMA_CPL_STATUS_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_DMA_CPL_STATUS_ADDR % 4u) == 0u, "dma.CPL_STATUS is not naturally aligned");
#define SF_DMA_CPL_STATUS_VALID_SHIFT 0u
#define SF_DMA_CPL_STATUS_VALID_WIDTH 1u
#define SF_DMA_CPL_STATUS_VALID_MASK UINT32_C(0x1)
#define SF_DMA_CPL_STATUS_VALID_RESET UINT32_C(0x0)
#define SF_DMA_CPL_STATUS_ERR_SHIFT 1u
#define SF_DMA_CPL_STATUS_ERR_WIDTH 1u
#define SF_DMA_CPL_STATUS_ERR_MASK UINT32_C(0x2)
#define SF_DMA_CPL_STATUS_ERR_RESET UINT32_C(0x0)
#define SF_DMA_CPL_STATUS_CODE_SHIFT 4u
#define SF_DMA_CPL_STATUS_CODE_WIDTH 4u
#define SF_DMA_CPL_STATUS_CODE_MASK UINT32_C(0xf0)
#define SF_DMA_CPL_STATUS_CODE_RESET UINT32_C(0x0)
#define SF_DMA_CPL_STATUS_TAG_SHIFT 8u
#define SF_DMA_CPL_STATUS_TAG_WIDTH 8u
#define SF_DMA_CPL_STATUS_TAG_MASK UINT32_C(0xff00)
#define SF_DMA_CPL_STATUS_TAG_RESET UINT32_C(0x0)
static inline uint32_t sf_dma_cpl_status_read(void)
{
    return sf_regs_rd32_(SF_DMA_CPL_STATUS_ADDR);
}
static inline uint32_t sf_dma_cpl_status_get_valid(uint32_t reg)
{
    return (reg & SF_DMA_CPL_STATUS_VALID_MASK) >> SF_DMA_CPL_STATUS_VALID_SHIFT;
}
static inline uint32_t sf_dma_cpl_status_get_err(uint32_t reg)
{
    return (reg & SF_DMA_CPL_STATUS_ERR_MASK) >> SF_DMA_CPL_STATUS_ERR_SHIFT;
}
static inline uint32_t sf_dma_cpl_status_get_code(uint32_t reg)
{
    return (reg & SF_DMA_CPL_STATUS_CODE_MASK) >> SF_DMA_CPL_STATUS_CODE_SHIFT;
}
static inline uint32_t sf_dma_cpl_status_get_tag(uint32_t reg)
{
    return (reg & SF_DMA_CPL_STATUS_TAG_MASK) >> SF_DMA_CPL_STATUS_TAG_SHIFT;
}

/* dma.CPL_ERR_ADDR: 32-bit @ offset 0x24 - Address associated with a bus or region error */
#define SF_DMA_CPL_ERR_ADDR_OFFSET UINT64_C(0x24)
#define SF_DMA_CPL_ERR_ADDR_ADDR UINT64_C(0x120000024)
#define SF_DMA_CPL_ERR_ADDR_WIDTH 32u
#define SF_DMA_CPL_ERR_ADDR_RESET UINT32_C(0x0)
#define SF_DMA_CPL_ERR_ADDR_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_DMA_CPL_ERR_ADDR_ADDR % 4u) == 0u, "dma.CPL_ERR_ADDR is not naturally aligned");
#define SF_DMA_CPL_ERR_ADDR_VALUE_SHIFT 0u
#define SF_DMA_CPL_ERR_ADDR_VALUE_WIDTH 32u
#define SF_DMA_CPL_ERR_ADDR_VALUE_MASK UINT32_C(0xffffffff)
#define SF_DMA_CPL_ERR_ADDR_VALUE_RESET UINT32_C(0x0)
static inline uint32_t sf_dma_cpl_err_addr_read(void)
{
    return sf_regs_rd32_(SF_DMA_CPL_ERR_ADDR_ADDR);
}
static inline uint32_t sf_dma_cpl_err_addr_get_value(uint32_t reg)
{
    return (reg & SF_DMA_CPL_ERR_ADDR_VALUE_MASK) >> SF_DMA_CPL_ERR_ADDR_VALUE_SHIFT;
}

/* dma.CPL_BYTES: 32-bit @ offset 0x28 - Bytes written and acknowledged (contiguous prefix) */
#define SF_DMA_CPL_BYTES_OFFSET UINT64_C(0x28)
#define SF_DMA_CPL_BYTES_ADDR UINT64_C(0x120000028)
#define SF_DMA_CPL_BYTES_WIDTH 32u
#define SF_DMA_CPL_BYTES_RESET UINT32_C(0x0)
#define SF_DMA_CPL_BYTES_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_DMA_CPL_BYTES_ADDR % 4u) == 0u, "dma.CPL_BYTES is not naturally aligned");
#define SF_DMA_CPL_BYTES_VALUE_SHIFT 0u
#define SF_DMA_CPL_BYTES_VALUE_WIDTH 32u
#define SF_DMA_CPL_BYTES_VALUE_MASK UINT32_C(0xffffffff)
#define SF_DMA_CPL_BYTES_VALUE_RESET UINT32_C(0x0)
static inline uint32_t sf_dma_cpl_bytes_read(void)
{
    return sf_regs_rd32_(SF_DMA_CPL_BYTES_ADDR);
}
static inline uint32_t sf_dma_cpl_bytes_get_value(uint32_t reg)
{
    return (reg & SF_DMA_CPL_BYTES_VALUE_MASK) >> SF_DMA_CPL_BYTES_VALUE_SHIFT;
}

/* dma.CPL_POP: 32-bit @ offset 0x2c - Release the head completion record. Refused (TARGET_ERR) when there is none. */
#define SF_DMA_CPL_POP_OFFSET UINT64_C(0x2c)
#define SF_DMA_CPL_POP_ADDR UINT64_C(0x12000002c)
#define SF_DMA_CPL_POP_WIDTH 32u
#define SF_DMA_CPL_POP_RESET UINT32_C(0x0)
#define SF_DMA_CPL_POP_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_DMA_CPL_POP_ADDR % 4u) == 0u, "dma.CPL_POP is not naturally aligned");
#define SF_DMA_CPL_POP_POP_SHIFT 0u
#define SF_DMA_CPL_POP_POP_WIDTH 32u
#define SF_DMA_CPL_POP_POP_MASK UINT32_C(0xffffffff)
#define SF_DMA_CPL_POP_POP_RESET UINT32_C(0x0)
static inline void sf_dma_cpl_pop_write(uint32_t value)
{
    sf_regs_wr32_(SF_DMA_CPL_POP_ADDR, value);
}
static inline uint32_t sf_dma_cpl_pop_pop_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_DMA_CPL_POP_POP_SHIFT) & SF_DMA_CPL_POP_POP_MASK;
}

/* dma.PERF_CTRL: 32-bit @ offset 0x30 - Performance counter control */
#define SF_DMA_PERF_CTRL_OFFSET UINT64_C(0x30)
#define SF_DMA_PERF_CTRL_ADDR UINT64_C(0x120000030)
#define SF_DMA_PERF_CTRL_WIDTH 32u
#define SF_DMA_PERF_CTRL_RESET UINT32_C(0x0)
#define SF_DMA_PERF_CTRL_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_DMA_PERF_CTRL_ADDR % 4u) == 0u, "dma.PERF_CTRL is not naturally aligned");
#define SF_DMA_PERF_CTRL_CLEAR_SHIFT 0u
#define SF_DMA_PERF_CTRL_CLEAR_WIDTH 1u
#define SF_DMA_PERF_CTRL_CLEAR_MASK UINT32_C(0x1)
#define SF_DMA_PERF_CTRL_CLEAR_RESET UINT32_C(0x0)
static inline void sf_dma_perf_ctrl_write(uint32_t value)
{
    sf_regs_wr32_(SF_DMA_PERF_CTRL_ADDR, value);
}
static inline uint32_t sf_dma_perf_ctrl_clear_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_DMA_PERF_CTRL_CLEAR_SHIFT) & SF_DMA_PERF_CTRL_CLEAR_MASK;
}
/* w1p: write 1 to the chosen bits of CLEAR (pulse); other rw fields keep their value, other write-one fields get 0. */
static inline void sf_dma_perf_ctrl_pulse_clear(uint32_t bits)
{
    sf_dma_perf_ctrl_write(sf_dma_perf_ctrl_clear_encode(bits));
}

/* dma.INT_ENABLE: 32-bit @ offset 0x34 - Interrupt enables */
#define SF_DMA_INT_ENABLE_OFFSET UINT64_C(0x34)
#define SF_DMA_INT_ENABLE_ADDR UINT64_C(0x120000034)
#define SF_DMA_INT_ENABLE_WIDTH 32u
#define SF_DMA_INT_ENABLE_RESET UINT32_C(0x0)
#define SF_DMA_INT_ENABLE_RW_MASK UINT32_C(0xf)
SF_REGS_STATIC_ASSERT((SF_DMA_INT_ENABLE_ADDR % 4u) == 0u, "dma.INT_ENABLE is not naturally aligned");
#define SF_DMA_INT_ENABLE_CPL_SHIFT 0u
#define SF_DMA_INT_ENABLE_CPL_WIDTH 1u
#define SF_DMA_INT_ENABLE_CPL_MASK UINT32_C(0x1)
#define SF_DMA_INT_ENABLE_CPL_RESET UINT32_C(0x0)
#define SF_DMA_INT_ENABLE_CPL_ERR_SHIFT 1u
#define SF_DMA_INT_ENABLE_CPL_ERR_WIDTH 1u
#define SF_DMA_INT_ENABLE_CPL_ERR_MASK UINT32_C(0x2)
#define SF_DMA_INT_ENABLE_CPL_ERR_RESET UINT32_C(0x0)
#define SF_DMA_INT_ENABLE_BUS_ERR_SHIFT 2u
#define SF_DMA_INT_ENABLE_BUS_ERR_WIDTH 1u
#define SF_DMA_INT_ENABLE_BUS_ERR_MASK UINT32_C(0x4)
#define SF_DMA_INT_ENABLE_BUS_ERR_RESET UINT32_C(0x0)
#define SF_DMA_INT_ENABLE_TAG_ERR_SHIFT 3u
#define SF_DMA_INT_ENABLE_TAG_ERR_WIDTH 1u
#define SF_DMA_INT_ENABLE_TAG_ERR_MASK UINT32_C(0x8)
#define SF_DMA_INT_ENABLE_TAG_ERR_RESET UINT32_C(0x0)
static inline uint32_t sf_dma_int_enable_read(void)
{
    return sf_regs_rd32_(SF_DMA_INT_ENABLE_ADDR);
}
static inline void sf_dma_int_enable_write(uint32_t value)
{
    sf_regs_wr32_(SF_DMA_INT_ENABLE_ADDR, value);
}
static inline uint32_t sf_dma_int_enable_get_cpl(uint32_t reg)
{
    return (reg & SF_DMA_INT_ENABLE_CPL_MASK) >> SF_DMA_INT_ENABLE_CPL_SHIFT;
}
static inline uint32_t sf_dma_int_enable_cpl_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_DMA_INT_ENABLE_CPL_SHIFT) & SF_DMA_INT_ENABLE_CPL_MASK;
}
/* RMW of rw field CPL: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_dma_int_enable_set_cpl(uint32_t value)
{
    uint32_t v = sf_dma_int_enable_read() & SF_DMA_INT_ENABLE_RW_MASK;
    v = (v & ~SF_DMA_INT_ENABLE_CPL_MASK) | sf_dma_int_enable_cpl_encode(value);
    sf_dma_int_enable_write(v);
}
static inline uint32_t sf_dma_int_enable_get_cpl_err(uint32_t reg)
{
    return (reg & SF_DMA_INT_ENABLE_CPL_ERR_MASK) >> SF_DMA_INT_ENABLE_CPL_ERR_SHIFT;
}
static inline uint32_t sf_dma_int_enable_cpl_err_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_DMA_INT_ENABLE_CPL_ERR_SHIFT) & SF_DMA_INT_ENABLE_CPL_ERR_MASK;
}
/* RMW of rw field CPL_ERR: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_dma_int_enable_set_cpl_err(uint32_t value)
{
    uint32_t v = sf_dma_int_enable_read() & SF_DMA_INT_ENABLE_RW_MASK;
    v = (v & ~SF_DMA_INT_ENABLE_CPL_ERR_MASK) | sf_dma_int_enable_cpl_err_encode(value);
    sf_dma_int_enable_write(v);
}
static inline uint32_t sf_dma_int_enable_get_bus_err(uint32_t reg)
{
    return (reg & SF_DMA_INT_ENABLE_BUS_ERR_MASK) >> SF_DMA_INT_ENABLE_BUS_ERR_SHIFT;
}
static inline uint32_t sf_dma_int_enable_bus_err_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_DMA_INT_ENABLE_BUS_ERR_SHIFT) & SF_DMA_INT_ENABLE_BUS_ERR_MASK;
}
/* RMW of rw field BUS_ERR: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_dma_int_enable_set_bus_err(uint32_t value)
{
    uint32_t v = sf_dma_int_enable_read() & SF_DMA_INT_ENABLE_RW_MASK;
    v = (v & ~SF_DMA_INT_ENABLE_BUS_ERR_MASK) | sf_dma_int_enable_bus_err_encode(value);
    sf_dma_int_enable_write(v);
}
static inline uint32_t sf_dma_int_enable_get_tag_err(uint32_t reg)
{
    return (reg & SF_DMA_INT_ENABLE_TAG_ERR_MASK) >> SF_DMA_INT_ENABLE_TAG_ERR_SHIFT;
}
static inline uint32_t sf_dma_int_enable_tag_err_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_DMA_INT_ENABLE_TAG_ERR_SHIFT) & SF_DMA_INT_ENABLE_TAG_ERR_MASK;
}
/* RMW of rw field TAG_ERR: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_dma_int_enable_set_tag_err(uint32_t value)
{
    uint32_t v = sf_dma_int_enable_read() & SF_DMA_INT_ENABLE_RW_MASK;
    v = (v & ~SF_DMA_INT_ENABLE_TAG_ERR_MASK) | sf_dma_int_enable_tag_err_encode(value);
    sf_dma_int_enable_write(v);
}

/* dma.INT_STATUS: 32-bit @ offset 0x38 - Interrupt status (write 1 to clear; a same-cycle hardware event wins) */
#define SF_DMA_INT_STATUS_OFFSET UINT64_C(0x38)
#define SF_DMA_INT_STATUS_ADDR UINT64_C(0x120000038)
#define SF_DMA_INT_STATUS_WIDTH 32u
#define SF_DMA_INT_STATUS_RESET UINT32_C(0x0)
#define SF_DMA_INT_STATUS_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_DMA_INT_STATUS_ADDR % 4u) == 0u, "dma.INT_STATUS is not naturally aligned");
#define SF_DMA_INT_STATUS_CPL_SHIFT 0u
#define SF_DMA_INT_STATUS_CPL_WIDTH 1u
#define SF_DMA_INT_STATUS_CPL_MASK UINT32_C(0x1)
#define SF_DMA_INT_STATUS_CPL_RESET UINT32_C(0x0)
#define SF_DMA_INT_STATUS_CPL_ERR_SHIFT 1u
#define SF_DMA_INT_STATUS_CPL_ERR_WIDTH 1u
#define SF_DMA_INT_STATUS_CPL_ERR_MASK UINT32_C(0x2)
#define SF_DMA_INT_STATUS_CPL_ERR_RESET UINT32_C(0x0)
#define SF_DMA_INT_STATUS_BUS_ERR_SHIFT 2u
#define SF_DMA_INT_STATUS_BUS_ERR_WIDTH 1u
#define SF_DMA_INT_STATUS_BUS_ERR_MASK UINT32_C(0x4)
#define SF_DMA_INT_STATUS_BUS_ERR_RESET UINT32_C(0x0)
#define SF_DMA_INT_STATUS_TAG_ERR_SHIFT 3u
#define SF_DMA_INT_STATUS_TAG_ERR_WIDTH 1u
#define SF_DMA_INT_STATUS_TAG_ERR_MASK UINT32_C(0x8)
#define SF_DMA_INT_STATUS_TAG_ERR_RESET UINT32_C(0x0)
static inline uint32_t sf_dma_int_status_read(void)
{
    return sf_regs_rd32_(SF_DMA_INT_STATUS_ADDR);
}
static inline void sf_dma_int_status_write(uint32_t value)
{
    sf_regs_wr32_(SF_DMA_INT_STATUS_ADDR, value);
}
static inline uint32_t sf_dma_int_status_get_cpl(uint32_t reg)
{
    return (reg & SF_DMA_INT_STATUS_CPL_MASK) >> SF_DMA_INT_STATUS_CPL_SHIFT;
}
static inline uint32_t sf_dma_int_status_cpl_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_DMA_INT_STATUS_CPL_SHIFT) & SF_DMA_INT_STATUS_CPL_MASK;
}
/* w1c: write 1 to the chosen bits of CPL (clear); other rw fields keep their value, other write-one fields get 0. */
static inline void sf_dma_int_status_clear_cpl(uint32_t bits)
{
    sf_dma_int_status_write(sf_dma_int_status_cpl_encode(bits));
}
static inline uint32_t sf_dma_int_status_get_cpl_err(uint32_t reg)
{
    return (reg & SF_DMA_INT_STATUS_CPL_ERR_MASK) >> SF_DMA_INT_STATUS_CPL_ERR_SHIFT;
}
static inline uint32_t sf_dma_int_status_cpl_err_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_DMA_INT_STATUS_CPL_ERR_SHIFT) & SF_DMA_INT_STATUS_CPL_ERR_MASK;
}
/* w1c: write 1 to the chosen bits of CPL_ERR (clear); other rw fields keep their value, other write-one fields get 0. */
static inline void sf_dma_int_status_clear_cpl_err(uint32_t bits)
{
    sf_dma_int_status_write(sf_dma_int_status_cpl_err_encode(bits));
}
static inline uint32_t sf_dma_int_status_get_bus_err(uint32_t reg)
{
    return (reg & SF_DMA_INT_STATUS_BUS_ERR_MASK) >> SF_DMA_INT_STATUS_BUS_ERR_SHIFT;
}
static inline uint32_t sf_dma_int_status_bus_err_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_DMA_INT_STATUS_BUS_ERR_SHIFT) & SF_DMA_INT_STATUS_BUS_ERR_MASK;
}
/* w1c: write 1 to the chosen bits of BUS_ERR (clear); other rw fields keep their value, other write-one fields get 0. */
static inline void sf_dma_int_status_clear_bus_err(uint32_t bits)
{
    sf_dma_int_status_write(sf_dma_int_status_bus_err_encode(bits));
}
static inline uint32_t sf_dma_int_status_get_tag_err(uint32_t reg)
{
    return (reg & SF_DMA_INT_STATUS_TAG_ERR_MASK) >> SF_DMA_INT_STATUS_TAG_ERR_SHIFT;
}
static inline uint32_t sf_dma_int_status_tag_err_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_DMA_INT_STATUS_TAG_ERR_SHIFT) & SF_DMA_INT_STATUS_TAG_ERR_MASK;
}
/* w1c: write 1 to the chosen bits of TAG_ERR (clear); other rw fields keep their value, other write-one fields get 0. */
static inline void sf_dma_int_status_clear_tag_err(uint32_t bits)
{
    sf_dma_int_status_write(sf_dma_int_status_tag_err_encode(bits));
}

/* dma.PERF[16]: 32-bit array of 16, stride 4 @ offset 0x40 - Performance counter i (hpc_dma_perf): 0 CYCLES, 1 ACTIVE, 2 BYTES_RD, 3 BYTES_WR, 4 READS, 5 WRITES, 6 REQ_STALL, 7 RSP_WAIT, 8 OUT_SUM, 9 OUT_MAX, 10 CPL_OK, 11 CPL_ERR, 12 BUS_ERR, 13 TAG_ERR, 14 SPM_REQ, 15 FAB_REQ */
#define SF_DMA_PERF_OFFSET UINT64_C(0x40)
#define SF_DMA_PERF_ADDR UINT64_C(0x120000040)
#define SF_DMA_PERF_WIDTH 32u
#define SF_DMA_PERF_RESET UINT32_C(0x0)
#define SF_DMA_PERF_RW_MASK UINT32_C(0x0)
#define SF_DMA_PERF_COUNT 16u
#define SF_DMA_PERF_STRIDE UINT64_C(4)
SF_REGS_STATIC_ASSERT((SF_DMA_PERF_ADDR % 4u) == 0u, "dma.PERF is not naturally aligned");
#define SF_DMA_PERF_VALUE_SHIFT 0u
#define SF_DMA_PERF_VALUE_WIDTH 32u
#define SF_DMA_PERF_VALUE_MASK UINT32_C(0xffffffff)
#define SF_DMA_PERF_VALUE_RESET UINT32_C(0x0)
static inline uint64_t sf_dma_perf_addr(unsigned i)
{
    if (i >= SF_DMA_PERF_COUNT) { SF_REGS_FAULT(); }
    return SF_DMA_PERF_ADDR + (uint64_t)i * SF_DMA_PERF_STRIDE;
}
static inline uint32_t sf_dma_perf_read(unsigned i)
{
    return sf_regs_rd32_(sf_dma_perf_addr(i));
}
static inline uint32_t sf_dma_perf_get_value(uint32_t reg)
{
    return (reg & SF_DMA_PERF_VALUE_MASK) >> SF_DMA_PERF_VALUE_SHIFT;
}

/* ---------- tensor: Tensor accelerator command interface (GEMM descriptors, completions, counters) ---------- */
/* region tensor_vector; window 0x150000000 + 0x1000 */

/* tensor.ID: 32-bit @ offset 0x0 - ASCII "SFTC" */
#define SF_TENSOR_ID_OFFSET UINT64_C(0x0)
#define SF_TENSOR_ID_ADDR UINT64_C(0x150000000)
#define SF_TENSOR_ID_WIDTH 32u
#define SF_TENSOR_ID_RESET UINT32_C(0x53465443)
#define SF_TENSOR_ID_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_TENSOR_ID_ADDR % 4u) == 0u, "tensor.ID is not naturally aligned");
#define SF_TENSOR_ID_VALUE_SHIFT 0u
#define SF_TENSOR_ID_VALUE_WIDTH 32u
#define SF_TENSOR_ID_VALUE_MASK UINT32_C(0xffffffff)
#define SF_TENSOR_ID_VALUE_RESET UINT32_C(0x53465443)
static inline uint32_t sf_tensor_id_read(void)
{
    return sf_regs_rd32_(SF_TENSOR_ID_ADDR);
}
static inline uint32_t sf_tensor_id_get_value(uint32_t reg)
{
    return (reg & SF_TENSOR_ID_VALUE_MASK) >> SF_TENSOR_ID_VALUE_SHIFT;
}

/* tensor.INFO: 32-bit @ offset 0x4 - Build configuration (from the instantiation parameters) */
#define SF_TENSOR_INFO_OFFSET UINT64_C(0x4)
#define SF_TENSOR_INFO_ADDR UINT64_C(0x150000004)
#define SF_TENSOR_INFO_WIDTH 32u
#define SF_TENSOR_INFO_RESET UINT32_C(0x0)
#define SF_TENSOR_INFO_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_TENSOR_INFO_ADDR % 4u) == 0u, "tensor.INFO is not naturally aligned");
#define SF_TENSOR_INFO_ABI_VERSION_SHIFT 0u
#define SF_TENSOR_INFO_ABI_VERSION_WIDTH 4u
#define SF_TENSOR_INFO_ABI_VERSION_MASK UINT32_C(0xf)
#define SF_TENSOR_INFO_ABI_VERSION_RESET UINT32_C(0x0)
#define SF_TENSOR_INFO_LOG2_QUEUE_DEPTH_SHIFT 4u
#define SF_TENSOR_INFO_LOG2_QUEUE_DEPTH_WIDTH 4u
#define SF_TENSOR_INFO_LOG2_QUEUE_DEPTH_MASK UINT32_C(0xf0)
#define SF_TENSOR_INFO_LOG2_QUEUE_DEPTH_RESET UINT32_C(0x0)
#define SF_TENSOR_INFO_ARRAY_ROWS_SHIFT 8u
#define SF_TENSOR_INFO_ARRAY_ROWS_WIDTH 8u
#define SF_TENSOR_INFO_ARRAY_ROWS_MASK UINT32_C(0xff00)
#define SF_TENSOR_INFO_ARRAY_ROWS_RESET UINT32_C(0x0)
#define SF_TENSOR_INFO_ARRAY_COLS_SHIFT 16u
#define SF_TENSOR_INFO_ARRAY_COLS_WIDTH 8u
#define SF_TENSOR_INFO_ARRAY_COLS_MASK UINT32_C(0xff0000)
#define SF_TENSOR_INFO_ARRAY_COLS_RESET UINT32_C(0x0)
#define SF_TENSOR_INFO_ENABLE_QUANTIZATION_SHIFT 24u
#define SF_TENSOR_INFO_ENABLE_QUANTIZATION_WIDTH 1u
#define SF_TENSOR_INFO_ENABLE_QUANTIZATION_MASK UINT32_C(0x1000000)
#define SF_TENSOR_INFO_ENABLE_QUANTIZATION_RESET UINT32_C(0x0)
#define SF_TENSOR_INFO_ENABLE_DOUBLE_BUFFERING_SHIFT 25u
#define SF_TENSOR_INFO_ENABLE_DOUBLE_BUFFERING_WIDTH 1u
#define SF_TENSOR_INFO_ENABLE_DOUBLE_BUFFERING_MASK UINT32_C(0x2000000)
#define SF_TENSOR_INFO_ENABLE_DOUBLE_BUFFERING_RESET UINT32_C(0x0)
#define SF_TENSOR_INFO_PERF_EN_SHIFT 26u
#define SF_TENSOR_INFO_PERF_EN_WIDTH 1u
#define SF_TENSOR_INFO_PERF_EN_MASK UINT32_C(0x4000000)
#define SF_TENSOR_INFO_PERF_EN_RESET UINT32_C(0x0)
static inline uint32_t sf_tensor_info_read(void)
{
    return sf_regs_rd32_(SF_TENSOR_INFO_ADDR);
}
static inline uint32_t sf_tensor_info_get_abi_version(uint32_t reg)
{
    return (reg & SF_TENSOR_INFO_ABI_VERSION_MASK) >> SF_TENSOR_INFO_ABI_VERSION_SHIFT;
}
static inline uint32_t sf_tensor_info_get_log2_queue_depth(uint32_t reg)
{
    return (reg & SF_TENSOR_INFO_LOG2_QUEUE_DEPTH_MASK) >> SF_TENSOR_INFO_LOG2_QUEUE_DEPTH_SHIFT;
}
static inline uint32_t sf_tensor_info_get_array_rows(uint32_t reg)
{
    return (reg & SF_TENSOR_INFO_ARRAY_ROWS_MASK) >> SF_TENSOR_INFO_ARRAY_ROWS_SHIFT;
}
static inline uint32_t sf_tensor_info_get_array_cols(uint32_t reg)
{
    return (reg & SF_TENSOR_INFO_ARRAY_COLS_MASK) >> SF_TENSOR_INFO_ARRAY_COLS_SHIFT;
}
static inline uint32_t sf_tensor_info_get_enable_quantization(uint32_t reg)
{
    return (reg & SF_TENSOR_INFO_ENABLE_QUANTIZATION_MASK) >> SF_TENSOR_INFO_ENABLE_QUANTIZATION_SHIFT;
}
static inline uint32_t sf_tensor_info_get_enable_double_buffering(uint32_t reg)
{
    return (reg & SF_TENSOR_INFO_ENABLE_DOUBLE_BUFFERING_MASK) >> SF_TENSOR_INFO_ENABLE_DOUBLE_BUFFERING_SHIFT;
}
static inline uint32_t sf_tensor_info_get_perf_en(uint32_t reg)
{
    return (reg & SF_TENSOR_INFO_PERF_EN_MASK) >> SF_TENSOR_INFO_PERF_EN_SHIFT;
}

/* tensor.CAPS: 32-bit @ offset 0x8 - Datapath capabilities */
#define SF_TENSOR_CAPS_OFFSET UINT64_C(0x8)
#define SF_TENSOR_CAPS_ADDR UINT64_C(0x150000008)
#define SF_TENSOR_CAPS_WIDTH 32u
#define SF_TENSOR_CAPS_RESET UINT32_C(0x0)
#define SF_TENSOR_CAPS_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_TENSOR_CAPS_ADDR % 4u) == 0u, "tensor.CAPS is not naturally aligned");
#define SF_TENSOR_CAPS_TILE_K_SHIFT 0u
#define SF_TENSOR_CAPS_TILE_K_WIDTH 16u
#define SF_TENSOR_CAPS_TILE_K_MASK UINT32_C(0xffff)
#define SF_TENSOR_CAPS_TILE_K_RESET UINT32_C(0x0)
#define SF_TENSOR_CAPS_DATA_WIDTH_SHIFT 16u
#define SF_TENSOR_CAPS_DATA_WIDTH_WIDTH 8u
#define SF_TENSOR_CAPS_DATA_WIDTH_MASK UINT32_C(0xff0000)
#define SF_TENSOR_CAPS_DATA_WIDTH_RESET UINT32_C(0x0)
#define SF_TENSOR_CAPS_ACC_WIDTH_SHIFT 24u
#define SF_TENSOR_CAPS_ACC_WIDTH_WIDTH 8u
#define SF_TENSOR_CAPS_ACC_WIDTH_MASK UINT32_C(0xff000000)
#define SF_TENSOR_CAPS_ACC_WIDTH_RESET UINT32_C(0x0)
static inline uint32_t sf_tensor_caps_read(void)
{
    return sf_regs_rd32_(SF_TENSOR_CAPS_ADDR);
}
static inline uint32_t sf_tensor_caps_get_tile_k(uint32_t reg)
{
    return (reg & SF_TENSOR_CAPS_TILE_K_MASK) >> SF_TENSOR_CAPS_TILE_K_SHIFT;
}
static inline uint32_t sf_tensor_caps_get_data_width(uint32_t reg)
{
    return (reg & SF_TENSOR_CAPS_DATA_WIDTH_MASK) >> SF_TENSOR_CAPS_DATA_WIDTH_SHIFT;
}
static inline uint32_t sf_tensor_caps_get_acc_width(uint32_t reg)
{
    return (reg & SF_TENSOR_CAPS_ACC_WIDTH_MASK) >> SF_TENSOR_CAPS_ACC_WIDTH_SHIFT;
}

/* tensor.OPBUF: 32-bit @ offset 0xc - Operand buffer size in bytes */
#define SF_TENSOR_OPBUF_OFFSET UINT64_C(0xc)
#define SF_TENSOR_OPBUF_ADDR UINT64_C(0x15000000c)
#define SF_TENSOR_OPBUF_WIDTH 32u
#define SF_TENSOR_OPBUF_RESET UINT32_C(0x0)
#define SF_TENSOR_OPBUF_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_TENSOR_OPBUF_ADDR % 4u) == 0u, "tensor.OPBUF is not naturally aligned");
#define SF_TENSOR_OPBUF_VALUE_SHIFT 0u
#define SF_TENSOR_OPBUF_VALUE_WIDTH 32u
#define SF_TENSOR_OPBUF_VALUE_MASK UINT32_C(0xffffffff)
#define SF_TENSOR_OPBUF_VALUE_RESET UINT32_C(0x0)
static inline uint32_t sf_tensor_opbuf_read(void)
{
    return sf_regs_rd32_(SF_TENSOR_OPBUF_ADDR);
}
static inline uint32_t sf_tensor_opbuf_get_value(uint32_t reg)
{
    return (reg & SF_TENSOR_OPBUF_VALUE_MASK) >> SF_TENSOR_OPBUF_VALUE_SHIFT;
}

/* tensor.MEM_LO: 32-bit @ offset 0x10 - First byte of the memory window the unit may access */
#define SF_TENSOR_MEM_LO_OFFSET UINT64_C(0x10)
#define SF_TENSOR_MEM_LO_ADDR UINT64_C(0x150000010)
#define SF_TENSOR_MEM_LO_WIDTH 32u
#define SF_TENSOR_MEM_LO_RESET UINT32_C(0x0)
#define SF_TENSOR_MEM_LO_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_TENSOR_MEM_LO_ADDR % 4u) == 0u, "tensor.MEM_LO is not naturally aligned");
#define SF_TENSOR_MEM_LO_VALUE_SHIFT 0u
#define SF_TENSOR_MEM_LO_VALUE_WIDTH 32u
#define SF_TENSOR_MEM_LO_VALUE_MASK UINT32_C(0xffffffff)
#define SF_TENSOR_MEM_LO_VALUE_RESET UINT32_C(0x0)
static inline uint32_t sf_tensor_mem_lo_read(void)
{
    return sf_regs_rd32_(SF_TENSOR_MEM_LO_ADDR);
}
static inline uint32_t sf_tensor_mem_lo_get_value(uint32_t reg)
{
    return (reg & SF_TENSOR_MEM_LO_VALUE_MASK) >> SF_TENSOR_MEM_LO_VALUE_SHIFT;
}

/* tensor.MEM_LAST: 32-bit @ offset 0x14 - Last byte of the memory window the unit may access */
#define SF_TENSOR_MEM_LAST_OFFSET UINT64_C(0x14)
#define SF_TENSOR_MEM_LAST_ADDR UINT64_C(0x150000014)
#define SF_TENSOR_MEM_LAST_WIDTH 32u
#define SF_TENSOR_MEM_LAST_RESET UINT32_C(0x0)
#define SF_TENSOR_MEM_LAST_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_TENSOR_MEM_LAST_ADDR % 4u) == 0u, "tensor.MEM_LAST is not naturally aligned");
#define SF_TENSOR_MEM_LAST_VALUE_SHIFT 0u
#define SF_TENSOR_MEM_LAST_VALUE_WIDTH 32u
#define SF_TENSOR_MEM_LAST_VALUE_MASK UINT32_C(0xffffffff)
#define SF_TENSOR_MEM_LAST_VALUE_RESET UINT32_C(0x0)
static inline uint32_t sf_tensor_mem_last_read(void)
{
    return sf_regs_rd32_(SF_TENSOR_MEM_LAST_ADDR);
}
static inline uint32_t sf_tensor_mem_last_get_value(uint32_t reg)
{
    return (reg & SF_TENSOR_MEM_LAST_VALUE_MASK) >> SF_TENSOR_MEM_LAST_VALUE_SHIFT;
}

/* tensor.CTRL: 32-bit @ offset 0x18 - Control */
#define SF_TENSOR_CTRL_OFFSET UINT64_C(0x18)
#define SF_TENSOR_CTRL_ADDR UINT64_C(0x150000018)
#define SF_TENSOR_CTRL_WIDTH 32u
#define SF_TENSOR_CTRL_RESET UINT32_C(0x0)
#define SF_TENSOR_CTRL_RW_MASK UINT32_C(0x1)
SF_REGS_STATIC_ASSERT((SF_TENSOR_CTRL_ADDR % 4u) == 0u, "tensor.CTRL is not naturally aligned");
#define SF_TENSOR_CTRL_ERR_CONT_SHIFT 0u
#define SF_TENSOR_CTRL_ERR_CONT_WIDTH 1u
#define SF_TENSOR_CTRL_ERR_CONT_MASK UINT32_C(0x1)
#define SF_TENSOR_CTRL_ERR_CONT_RESET UINT32_C(0x0)
#define SF_TENSOR_CTRL_ERR_CLEAR_SHIFT 1u
#define SF_TENSOR_CTRL_ERR_CLEAR_WIDTH 1u
#define SF_TENSOR_CTRL_ERR_CLEAR_MASK UINT32_C(0x2)
#define SF_TENSOR_CTRL_ERR_CLEAR_RESET UINT32_C(0x0)
#define SF_TENSOR_CTRL_PERF_CLEAR_SHIFT 2u
#define SF_TENSOR_CTRL_PERF_CLEAR_WIDTH 1u
#define SF_TENSOR_CTRL_PERF_CLEAR_MASK UINT32_C(0x4)
#define SF_TENSOR_CTRL_PERF_CLEAR_RESET UINT32_C(0x0)
#define SF_TENSOR_CTRL_ABORT_SHIFT 3u
#define SF_TENSOR_CTRL_ABORT_WIDTH 1u
#define SF_TENSOR_CTRL_ABORT_MASK UINT32_C(0x8)
#define SF_TENSOR_CTRL_ABORT_RESET UINT32_C(0x0)
static inline uint32_t sf_tensor_ctrl_read(void)
{
    return sf_regs_rd32_(SF_TENSOR_CTRL_ADDR);
}
static inline void sf_tensor_ctrl_write(uint32_t value)
{
    sf_regs_wr32_(SF_TENSOR_CTRL_ADDR, value);
}
static inline uint32_t sf_tensor_ctrl_get_err_cont(uint32_t reg)
{
    return (reg & SF_TENSOR_CTRL_ERR_CONT_MASK) >> SF_TENSOR_CTRL_ERR_CONT_SHIFT;
}
static inline uint32_t sf_tensor_ctrl_err_cont_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_TENSOR_CTRL_ERR_CONT_SHIFT) & SF_TENSOR_CTRL_ERR_CONT_MASK;
}
/* RMW of rw field ERR_CONT: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_tensor_ctrl_set_err_cont(uint32_t value)
{
    uint32_t v = sf_tensor_ctrl_read() & SF_TENSOR_CTRL_RW_MASK;
    v = (v & ~SF_TENSOR_CTRL_ERR_CONT_MASK) | sf_tensor_ctrl_err_cont_encode(value);
    sf_tensor_ctrl_write(v);
}
static inline uint32_t sf_tensor_ctrl_err_clear_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_TENSOR_CTRL_ERR_CLEAR_SHIFT) & SF_TENSOR_CTRL_ERR_CLEAR_MASK;
}
/* w1p: write 1 to the chosen bits of ERR_CLEAR (pulse); other rw fields keep their value, other write-one fields get 0. */
static inline void sf_tensor_ctrl_pulse_err_clear(uint32_t bits)
{
    uint32_t v = sf_tensor_ctrl_read() & SF_TENSOR_CTRL_RW_MASK;
    sf_tensor_ctrl_write(v | sf_tensor_ctrl_err_clear_encode(bits));
}
static inline uint32_t sf_tensor_ctrl_perf_clear_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_TENSOR_CTRL_PERF_CLEAR_SHIFT) & SF_TENSOR_CTRL_PERF_CLEAR_MASK;
}
/* w1p: write 1 to the chosen bits of PERF_CLEAR (pulse); other rw fields keep their value, other write-one fields get 0. */
static inline void sf_tensor_ctrl_pulse_perf_clear(uint32_t bits)
{
    uint32_t v = sf_tensor_ctrl_read() & SF_TENSOR_CTRL_RW_MASK;
    sf_tensor_ctrl_write(v | sf_tensor_ctrl_perf_clear_encode(bits));
}
static inline uint32_t sf_tensor_ctrl_abort_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_TENSOR_CTRL_ABORT_SHIFT) & SF_TENSOR_CTRL_ABORT_MASK;
}
/* w1p: write 1 to the chosen bits of ABORT (pulse); other rw fields keep their value, other write-one fields get 0. */
static inline void sf_tensor_ctrl_pulse_abort(uint32_t bits)
{
    uint32_t v = sf_tensor_ctrl_read() & SF_TENSOR_CTRL_RW_MASK;
    sf_tensor_ctrl_write(v | sf_tensor_ctrl_abort_encode(bits));
}

/* tensor.STATUS: 32-bit @ offset 0x1c - Unit status */
#define SF_TENSOR_STATUS_OFFSET UINT64_C(0x1c)
#define SF_TENSOR_STATUS_ADDR UINT64_C(0x15000001c)
#define SF_TENSOR_STATUS_WIDTH 32u
#define SF_TENSOR_STATUS_RESET UINT32_C(0x0)
#define SF_TENSOR_STATUS_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_TENSOR_STATUS_ADDR % 4u) == 0u, "tensor.STATUS is not naturally aligned");
#define SF_TENSOR_STATUS_BUSY_SHIFT 0u
#define SF_TENSOR_STATUS_BUSY_WIDTH 1u
#define SF_TENSOR_STATUS_BUSY_MASK UINT32_C(0x1)
#define SF_TENSOR_STATUS_BUSY_RESET UINT32_C(0x0)
#define SF_TENSOR_STATUS_ERR_STICKY_SHIFT 1u
#define SF_TENSOR_STATUS_ERR_STICKY_WIDTH 1u
#define SF_TENSOR_STATUS_ERR_STICKY_MASK UINT32_C(0x2)
#define SF_TENSOR_STATUS_ERR_STICKY_RESET UINT32_C(0x0)
#define SF_TENSOR_STATUS_Q_FULL_SHIFT 2u
#define SF_TENSOR_STATUS_Q_FULL_WIDTH 1u
#define SF_TENSOR_STATUS_Q_FULL_MASK UINT32_C(0x4)
#define SF_TENSOR_STATUS_Q_FULL_RESET UINT32_C(0x0)
#define SF_TENSOR_STATUS_Q_EMPTY_SHIFT 3u
#define SF_TENSOR_STATUS_Q_EMPTY_WIDTH 1u
#define SF_TENSOR_STATUS_Q_EMPTY_MASK UINT32_C(0x8)
#define SF_TENSOR_STATUS_Q_EMPTY_RESET UINT32_C(0x0)
#define SF_TENSOR_STATUS_CPL_VALID_SHIFT 4u
#define SF_TENSOR_STATUS_CPL_VALID_WIDTH 1u
#define SF_TENSOR_STATUS_CPL_VALID_MASK UINT32_C(0x10)
#define SF_TENSOR_STATUS_CPL_VALID_RESET UINT32_C(0x0)
#define SF_TENSOR_STATUS_ABORTING_SHIFT 5u
#define SF_TENSOR_STATUS_ABORTING_WIDTH 1u
#define SF_TENSOR_STATUS_ABORTING_MASK UINT32_C(0x20)
#define SF_TENSOR_STATUS_ABORTING_RESET UINT32_C(0x0)
#define SF_TENSOR_STATUS_HALTED_SHIFT 6u
#define SF_TENSOR_STATUS_HALTED_WIDTH 1u
#define SF_TENSOR_STATUS_HALTED_MASK UINT32_C(0x40)
#define SF_TENSOR_STATUS_HALTED_RESET UINT32_C(0x0)
#define SF_TENSOR_STATUS_STATE_SHIFT 8u
#define SF_TENSOR_STATUS_STATE_WIDTH 4u
#define SF_TENSOR_STATUS_STATE_MASK UINT32_C(0xf00)
#define SF_TENSOR_STATUS_STATE_RESET UINT32_C(0x0)
#define SF_TENSOR_STATUS_QCOUNT_SHIFT 16u
#define SF_TENSOR_STATUS_QCOUNT_WIDTH 8u
#define SF_TENSOR_STATUS_QCOUNT_MASK UINT32_C(0xff0000)
#define SF_TENSOR_STATUS_QCOUNT_RESET UINT32_C(0x0)
#define SF_TENSOR_STATUS_QFREE_SHIFT 24u
#define SF_TENSOR_STATUS_QFREE_WIDTH 8u
#define SF_TENSOR_STATUS_QFREE_MASK UINT32_C(0xff000000)
#define SF_TENSOR_STATUS_QFREE_RESET UINT32_C(0x0)
static inline uint32_t sf_tensor_status_read(void)
{
    return sf_regs_rd32_(SF_TENSOR_STATUS_ADDR);
}
static inline uint32_t sf_tensor_status_get_busy(uint32_t reg)
{
    return (reg & SF_TENSOR_STATUS_BUSY_MASK) >> SF_TENSOR_STATUS_BUSY_SHIFT;
}
static inline uint32_t sf_tensor_status_get_err_sticky(uint32_t reg)
{
    return (reg & SF_TENSOR_STATUS_ERR_STICKY_MASK) >> SF_TENSOR_STATUS_ERR_STICKY_SHIFT;
}
static inline uint32_t sf_tensor_status_get_q_full(uint32_t reg)
{
    return (reg & SF_TENSOR_STATUS_Q_FULL_MASK) >> SF_TENSOR_STATUS_Q_FULL_SHIFT;
}
static inline uint32_t sf_tensor_status_get_q_empty(uint32_t reg)
{
    return (reg & SF_TENSOR_STATUS_Q_EMPTY_MASK) >> SF_TENSOR_STATUS_Q_EMPTY_SHIFT;
}
static inline uint32_t sf_tensor_status_get_cpl_valid(uint32_t reg)
{
    return (reg & SF_TENSOR_STATUS_CPL_VALID_MASK) >> SF_TENSOR_STATUS_CPL_VALID_SHIFT;
}
static inline uint32_t sf_tensor_status_get_aborting(uint32_t reg)
{
    return (reg & SF_TENSOR_STATUS_ABORTING_MASK) >> SF_TENSOR_STATUS_ABORTING_SHIFT;
}
static inline uint32_t sf_tensor_status_get_halted(uint32_t reg)
{
    return (reg & SF_TENSOR_STATUS_HALTED_MASK) >> SF_TENSOR_STATUS_HALTED_SHIFT;
}
static inline uint32_t sf_tensor_status_get_state(uint32_t reg)
{
    return (reg & SF_TENSOR_STATUS_STATE_MASK) >> SF_TENSOR_STATUS_STATE_SHIFT;
}
static inline uint32_t sf_tensor_status_get_qcount(uint32_t reg)
{
    return (reg & SF_TENSOR_STATUS_QCOUNT_MASK) >> SF_TENSOR_STATUS_QCOUNT_SHIFT;
}
static inline uint32_t sf_tensor_status_get_qfree(uint32_t reg)
{
    return (reg & SF_TENSOR_STATUS_QFREE_MASK) >> SF_TENSOR_STATUS_QFREE_SHIFT;
}

/* tensor.INT_ENABLE: 32-bit @ offset 0x20 - Interrupt enables */
#define SF_TENSOR_INT_ENABLE_OFFSET UINT64_C(0x20)
#define SF_TENSOR_INT_ENABLE_ADDR UINT64_C(0x150000020)
#define SF_TENSOR_INT_ENABLE_WIDTH 32u
#define SF_TENSOR_INT_ENABLE_RESET UINT32_C(0x0)
#define SF_TENSOR_INT_ENABLE_RW_MASK UINT32_C(0x7)
SF_REGS_STATIC_ASSERT((SF_TENSOR_INT_ENABLE_ADDR % 4u) == 0u, "tensor.INT_ENABLE is not naturally aligned");
#define SF_TENSOR_INT_ENABLE_IRQ_SHIFT 0u
#define SF_TENSOR_INT_ENABLE_IRQ_WIDTH 1u
#define SF_TENSOR_INT_ENABLE_IRQ_MASK UINT32_C(0x1)
#define SF_TENSOR_INT_ENABLE_IRQ_RESET UINT32_C(0x0)
#define SF_TENSOR_INT_ENABLE_ERR_SHIFT 1u
#define SF_TENSOR_INT_ENABLE_ERR_WIDTH 1u
#define SF_TENSOR_INT_ENABLE_ERR_MASK UINT32_C(0x2)
#define SF_TENSOR_INT_ENABLE_ERR_RESET UINT32_C(0x0)
#define SF_TENSOR_INT_ENABLE_DONE_SHIFT 2u
#define SF_TENSOR_INT_ENABLE_DONE_WIDTH 1u
#define SF_TENSOR_INT_ENABLE_DONE_MASK UINT32_C(0x4)
#define SF_TENSOR_INT_ENABLE_DONE_RESET UINT32_C(0x0)
static inline uint32_t sf_tensor_int_enable_read(void)
{
    return sf_regs_rd32_(SF_TENSOR_INT_ENABLE_ADDR);
}
static inline void sf_tensor_int_enable_write(uint32_t value)
{
    sf_regs_wr32_(SF_TENSOR_INT_ENABLE_ADDR, value);
}
static inline uint32_t sf_tensor_int_enable_get_irq(uint32_t reg)
{
    return (reg & SF_TENSOR_INT_ENABLE_IRQ_MASK) >> SF_TENSOR_INT_ENABLE_IRQ_SHIFT;
}
static inline uint32_t sf_tensor_int_enable_irq_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_TENSOR_INT_ENABLE_IRQ_SHIFT) & SF_TENSOR_INT_ENABLE_IRQ_MASK;
}
/* RMW of rw field IRQ: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_tensor_int_enable_set_irq(uint32_t value)
{
    uint32_t v = sf_tensor_int_enable_read() & SF_TENSOR_INT_ENABLE_RW_MASK;
    v = (v & ~SF_TENSOR_INT_ENABLE_IRQ_MASK) | sf_tensor_int_enable_irq_encode(value);
    sf_tensor_int_enable_write(v);
}
static inline uint32_t sf_tensor_int_enable_get_err(uint32_t reg)
{
    return (reg & SF_TENSOR_INT_ENABLE_ERR_MASK) >> SF_TENSOR_INT_ENABLE_ERR_SHIFT;
}
static inline uint32_t sf_tensor_int_enable_err_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_TENSOR_INT_ENABLE_ERR_SHIFT) & SF_TENSOR_INT_ENABLE_ERR_MASK;
}
/* RMW of rw field ERR: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_tensor_int_enable_set_err(uint32_t value)
{
    uint32_t v = sf_tensor_int_enable_read() & SF_TENSOR_INT_ENABLE_RW_MASK;
    v = (v & ~SF_TENSOR_INT_ENABLE_ERR_MASK) | sf_tensor_int_enable_err_encode(value);
    sf_tensor_int_enable_write(v);
}
static inline uint32_t sf_tensor_int_enable_get_done(uint32_t reg)
{
    return (reg & SF_TENSOR_INT_ENABLE_DONE_MASK) >> SF_TENSOR_INT_ENABLE_DONE_SHIFT;
}
static inline uint32_t sf_tensor_int_enable_done_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_TENSOR_INT_ENABLE_DONE_SHIFT) & SF_TENSOR_INT_ENABLE_DONE_MASK;
}
/* RMW of rw field DONE: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_tensor_int_enable_set_done(uint32_t value)
{
    uint32_t v = sf_tensor_int_enable_read() & SF_TENSOR_INT_ENABLE_RW_MASK;
    v = (v & ~SF_TENSOR_INT_ENABLE_DONE_MASK) | sf_tensor_int_enable_done_encode(value);
    sf_tensor_int_enable_write(v);
}

/* tensor.INT_STATUS: 32-bit @ offset 0x24 - Interrupt status (write 1 to clear; a same-cycle hardware event wins) */
#define SF_TENSOR_INT_STATUS_OFFSET UINT64_C(0x24)
#define SF_TENSOR_INT_STATUS_ADDR UINT64_C(0x150000024)
#define SF_TENSOR_INT_STATUS_WIDTH 32u
#define SF_TENSOR_INT_STATUS_RESET UINT32_C(0x0)
#define SF_TENSOR_INT_STATUS_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_TENSOR_INT_STATUS_ADDR % 4u) == 0u, "tensor.INT_STATUS is not naturally aligned");
#define SF_TENSOR_INT_STATUS_IRQ_SHIFT 0u
#define SF_TENSOR_INT_STATUS_IRQ_WIDTH 1u
#define SF_TENSOR_INT_STATUS_IRQ_MASK UINT32_C(0x1)
#define SF_TENSOR_INT_STATUS_IRQ_RESET UINT32_C(0x0)
#define SF_TENSOR_INT_STATUS_ERR_SHIFT 1u
#define SF_TENSOR_INT_STATUS_ERR_WIDTH 1u
#define SF_TENSOR_INT_STATUS_ERR_MASK UINT32_C(0x2)
#define SF_TENSOR_INT_STATUS_ERR_RESET UINT32_C(0x0)
#define SF_TENSOR_INT_STATUS_DONE_SHIFT 2u
#define SF_TENSOR_INT_STATUS_DONE_WIDTH 1u
#define SF_TENSOR_INT_STATUS_DONE_MASK UINT32_C(0x4)
#define SF_TENSOR_INT_STATUS_DONE_RESET UINT32_C(0x0)
static inline uint32_t sf_tensor_int_status_read(void)
{
    return sf_regs_rd32_(SF_TENSOR_INT_STATUS_ADDR);
}
static inline void sf_tensor_int_status_write(uint32_t value)
{
    sf_regs_wr32_(SF_TENSOR_INT_STATUS_ADDR, value);
}
static inline uint32_t sf_tensor_int_status_get_irq(uint32_t reg)
{
    return (reg & SF_TENSOR_INT_STATUS_IRQ_MASK) >> SF_TENSOR_INT_STATUS_IRQ_SHIFT;
}
static inline uint32_t sf_tensor_int_status_irq_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_TENSOR_INT_STATUS_IRQ_SHIFT) & SF_TENSOR_INT_STATUS_IRQ_MASK;
}
/* w1c: write 1 to the chosen bits of IRQ (clear); other rw fields keep their value, other write-one fields get 0. */
static inline void sf_tensor_int_status_clear_irq(uint32_t bits)
{
    sf_tensor_int_status_write(sf_tensor_int_status_irq_encode(bits));
}
static inline uint32_t sf_tensor_int_status_get_err(uint32_t reg)
{
    return (reg & SF_TENSOR_INT_STATUS_ERR_MASK) >> SF_TENSOR_INT_STATUS_ERR_SHIFT;
}
static inline uint32_t sf_tensor_int_status_err_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_TENSOR_INT_STATUS_ERR_SHIFT) & SF_TENSOR_INT_STATUS_ERR_MASK;
}
/* w1c: write 1 to the chosen bits of ERR (clear); other rw fields keep their value, other write-one fields get 0. */
static inline void sf_tensor_int_status_clear_err(uint32_t bits)
{
    sf_tensor_int_status_write(sf_tensor_int_status_err_encode(bits));
}
static inline uint32_t sf_tensor_int_status_get_done(uint32_t reg)
{
    return (reg & SF_TENSOR_INT_STATUS_DONE_MASK) >> SF_TENSOR_INT_STATUS_DONE_SHIFT;
}
static inline uint32_t sf_tensor_int_status_done_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_TENSOR_INT_STATUS_DONE_SHIFT) & SF_TENSOR_INT_STATUS_DONE_MASK;
}
/* w1c: write 1 to the chosen bits of DONE (clear); other rw fields keep their value, other write-one fields get 0. */
static inline void sf_tensor_int_status_clear_done(uint32_t bits)
{
    sf_tensor_int_status_write(sf_tensor_int_status_done_encode(bits));
}

/* tensor.SUBMITTED: 32-bit @ offset 0x28 - Doorbells accepted since reset (glue counter) */
#define SF_TENSOR_SUBMITTED_OFFSET UINT64_C(0x28)
#define SF_TENSOR_SUBMITTED_ADDR UINT64_C(0x150000028)
#define SF_TENSOR_SUBMITTED_WIDTH 32u
#define SF_TENSOR_SUBMITTED_RESET UINT32_C(0x0)
#define SF_TENSOR_SUBMITTED_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_TENSOR_SUBMITTED_ADDR % 4u) == 0u, "tensor.SUBMITTED is not naturally aligned");
#define SF_TENSOR_SUBMITTED_VALUE_SHIFT 0u
#define SF_TENSOR_SUBMITTED_VALUE_WIDTH 32u
#define SF_TENSOR_SUBMITTED_VALUE_MASK UINT32_C(0xffffffff)
#define SF_TENSOR_SUBMITTED_VALUE_RESET UINT32_C(0x0)
static inline uint32_t sf_tensor_submitted_read(void)
{
    return sf_regs_rd32_(SF_TENSOR_SUBMITTED_ADDR);
}
static inline uint32_t sf_tensor_submitted_get_value(uint32_t reg)
{
    return (reg & SF_TENSOR_SUBMITTED_VALUE_MASK) >> SF_TENSOR_SUBMITTED_VALUE_SHIFT;
}

/* tensor.KMAX: 32-bit @ offset 0x2c - Largest legal K of this build */
#define SF_TENSOR_KMAX_OFFSET UINT64_C(0x2c)
#define SF_TENSOR_KMAX_ADDR UINT64_C(0x15000002c)
#define SF_TENSOR_KMAX_WIDTH 32u
#define SF_TENSOR_KMAX_RESET UINT32_C(0x0)
#define SF_TENSOR_KMAX_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_TENSOR_KMAX_ADDR % 4u) == 0u, "tensor.KMAX is not naturally aligned");
#define SF_TENSOR_KMAX_VALUE_SHIFT 0u
#define SF_TENSOR_KMAX_VALUE_WIDTH 32u
#define SF_TENSOR_KMAX_VALUE_MASK UINT32_C(0xffffffff)
#define SF_TENSOR_KMAX_VALUE_RESET UINT32_C(0x0)
static inline uint32_t sf_tensor_kmax_read(void)
{
    return sf_regs_rd32_(SF_TENSOR_KMAX_ADDR);
}
static inline uint32_t sf_tensor_kmax_get_value(uint32_t reg)
{
    return (reg & SF_TENSOR_KMAX_VALUE_MASK) >> SF_TENSOR_KMAX_VALUE_SHIFT;
}

/* tensor.DESC[12]: 32-bit array of 12, stride 4 @ offset 0x40 - Descriptor staging words 0..11 (kept after the doorbell) */
#define SF_TENSOR_DESC_OFFSET UINT64_C(0x40)
#define SF_TENSOR_DESC_ADDR UINT64_C(0x150000040)
#define SF_TENSOR_DESC_WIDTH 32u
#define SF_TENSOR_DESC_RESET UINT32_C(0x0)
#define SF_TENSOR_DESC_RW_MASK UINT32_C(0xffffffff)
#define SF_TENSOR_DESC_COUNT 12u
#define SF_TENSOR_DESC_STRIDE UINT64_C(4)
SF_REGS_STATIC_ASSERT((SF_TENSOR_DESC_ADDR % 4u) == 0u, "tensor.DESC is not naturally aligned");
#define SF_TENSOR_DESC_VALUE_SHIFT 0u
#define SF_TENSOR_DESC_VALUE_WIDTH 32u
#define SF_TENSOR_DESC_VALUE_MASK UINT32_C(0xffffffff)
#define SF_TENSOR_DESC_VALUE_RESET UINT32_C(0x0)
static inline uint64_t sf_tensor_desc_addr(unsigned i)
{
    if (i >= SF_TENSOR_DESC_COUNT) { SF_REGS_FAULT(); }
    return SF_TENSOR_DESC_ADDR + (uint64_t)i * SF_TENSOR_DESC_STRIDE;
}
static inline uint32_t sf_tensor_desc_read(unsigned i)
{
    return sf_regs_rd32_(sf_tensor_desc_addr(i));
}
static inline void sf_tensor_desc_write(unsigned i, uint32_t value)
{
    sf_regs_wr32_(sf_tensor_desc_addr(i), value);
}
static inline uint32_t sf_tensor_desc_get_value(uint32_t reg)
{
    return (reg & SF_TENSOR_DESC_VALUE_MASK) >> SF_TENSOR_DESC_VALUE_SHIFT;
}
static inline uint32_t sf_tensor_desc_value_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_TENSOR_DESC_VALUE_SHIFT) & SF_TENSOR_DESC_VALUE_MASK;
}
/* RMW of rw field VALUE: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_tensor_desc_set_value(unsigned i, uint32_t value)
{
    uint32_t v = sf_tensor_desc_read(i) & SF_TENSOR_DESC_RW_MASK;
    v = (v & ~SF_TENSOR_DESC_VALUE_MASK) | sf_tensor_desc_value_encode(value);
    sf_tensor_desc_write(i, v);
}

/* tensor.DOORBELL: 32-bit @ offset 0x70 - Submit the staged descriptor. Refused (TARGET_ERR) while the command queue is full. */
#define SF_TENSOR_DOORBELL_OFFSET UINT64_C(0x70)
#define SF_TENSOR_DOORBELL_ADDR UINT64_C(0x150000070)
#define SF_TENSOR_DOORBELL_WIDTH 32u
#define SF_TENSOR_DOORBELL_RESET UINT32_C(0x0)
#define SF_TENSOR_DOORBELL_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_TENSOR_DOORBELL_ADDR % 4u) == 0u, "tensor.DOORBELL is not naturally aligned");
#define SF_TENSOR_DOORBELL_RING_SHIFT 0u
#define SF_TENSOR_DOORBELL_RING_WIDTH 32u
#define SF_TENSOR_DOORBELL_RING_MASK UINT32_C(0xffffffff)
#define SF_TENSOR_DOORBELL_RING_RESET UINT32_C(0x0)
static inline void sf_tensor_doorbell_write(uint32_t value)
{
    sf_regs_wr32_(SF_TENSOR_DOORBELL_ADDR, value);
}
static inline uint32_t sf_tensor_doorbell_ring_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_TENSOR_DOORBELL_RING_SHIFT) & SF_TENSOR_DOORBELL_RING_MASK;
}

/* tensor.CPL[6]: 32-bit array of 6, stride 4 @ offset 0x80 - Head completion record words 0..5 (glue gates them with cpl_valid) */
#define SF_TENSOR_CPL_OFFSET UINT64_C(0x80)
#define SF_TENSOR_CPL_ADDR UINT64_C(0x150000080)
#define SF_TENSOR_CPL_WIDTH 32u
#define SF_TENSOR_CPL_RESET UINT32_C(0x0)
#define SF_TENSOR_CPL_RW_MASK UINT32_C(0x0)
#define SF_TENSOR_CPL_COUNT 6u
#define SF_TENSOR_CPL_STRIDE UINT64_C(4)
SF_REGS_STATIC_ASSERT((SF_TENSOR_CPL_ADDR % 4u) == 0u, "tensor.CPL is not naturally aligned");
#define SF_TENSOR_CPL_VALUE_SHIFT 0u
#define SF_TENSOR_CPL_VALUE_WIDTH 32u
#define SF_TENSOR_CPL_VALUE_MASK UINT32_C(0xffffffff)
#define SF_TENSOR_CPL_VALUE_RESET UINT32_C(0x0)
static inline uint64_t sf_tensor_cpl_addr(unsigned i)
{
    if (i >= SF_TENSOR_CPL_COUNT) { SF_REGS_FAULT(); }
    return SF_TENSOR_CPL_ADDR + (uint64_t)i * SF_TENSOR_CPL_STRIDE;
}
static inline uint32_t sf_tensor_cpl_read(unsigned i)
{
    return sf_regs_rd32_(sf_tensor_cpl_addr(i));
}
static inline uint32_t sf_tensor_cpl_get_value(uint32_t reg)
{
    return (reg & SF_TENSOR_CPL_VALUE_MASK) >> SF_TENSOR_CPL_VALUE_SHIFT;
}

/* tensor.CPL_POP: 32-bit @ offset 0x98 - Release the head record. Refused (TARGET_ERR) if there is none. */
#define SF_TENSOR_CPL_POP_OFFSET UINT64_C(0x98)
#define SF_TENSOR_CPL_POP_ADDR UINT64_C(0x150000098)
#define SF_TENSOR_CPL_POP_WIDTH 32u
#define SF_TENSOR_CPL_POP_RESET UINT32_C(0x0)
#define SF_TENSOR_CPL_POP_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_TENSOR_CPL_POP_ADDR % 4u) == 0u, "tensor.CPL_POP is not naturally aligned");
#define SF_TENSOR_CPL_POP_POP_SHIFT 0u
#define SF_TENSOR_CPL_POP_POP_WIDTH 32u
#define SF_TENSOR_CPL_POP_POP_MASK UINT32_C(0xffffffff)
#define SF_TENSOR_CPL_POP_POP_RESET UINT32_C(0x0)
static inline void sf_tensor_cpl_pop_write(uint32_t value)
{
    sf_regs_wr32_(SF_TENSOR_CPL_POP_ADDR, value);
}
static inline uint32_t sf_tensor_cpl_pop_pop_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_TENSOR_CPL_POP_POP_SHIFT) & SF_TENSOR_CPL_POP_POP_MASK;
}

/* tensor.PERF[20]: 32-bit array of 20, stride 4 @ offset 0x100 - Performance counter i (saturating 32-bit): 0 CYCLES, 1 BUSY, 2 CMD_ACCEPT, 3 CMD_DONE, 4 CMD_ERR, 5 GEMM_OK, 6 TILES, 7 CHUNKS, 8 MACS, 9 COMPUTE_CYC, 10 DMA_ACTIVE, 11 OVERLAP, 12 RD_WORDS, 13 WR_WORDS, 14 BUS_STALL, 15 DESC, 16 Q_FULL, 17 CPL_STALL, 18 SAT, 19 ABORTS */
#define SF_TENSOR_PERF_OFFSET UINT64_C(0x100)
#define SF_TENSOR_PERF_ADDR UINT64_C(0x150000100)
#define SF_TENSOR_PERF_WIDTH 32u
#define SF_TENSOR_PERF_RESET UINT32_C(0x0)
#define SF_TENSOR_PERF_RW_MASK UINT32_C(0x0)
#define SF_TENSOR_PERF_COUNT 20u
#define SF_TENSOR_PERF_STRIDE UINT64_C(4)
SF_REGS_STATIC_ASSERT((SF_TENSOR_PERF_ADDR % 4u) == 0u, "tensor.PERF is not naturally aligned");
#define SF_TENSOR_PERF_VALUE_SHIFT 0u
#define SF_TENSOR_PERF_VALUE_WIDTH 32u
#define SF_TENSOR_PERF_VALUE_MASK UINT32_C(0xffffffff)
#define SF_TENSOR_PERF_VALUE_RESET UINT32_C(0x0)
static inline uint64_t sf_tensor_perf_addr(unsigned i)
{
    if (i >= SF_TENSOR_PERF_COUNT) { SF_REGS_FAULT(); }
    return SF_TENSOR_PERF_ADDR + (uint64_t)i * SF_TENSOR_PERF_STRIDE;
}
static inline uint32_t sf_tensor_perf_read(unsigned i)
{
    return sf_regs_rd32_(sf_tensor_perf_addr(i));
}
static inline uint32_t sf_tensor_perf_get_value(uint32_t reg)
{
    return (reg & SF_TENSOR_PERF_VALUE_MASK) >> SF_TENSOR_PERF_VALUE_SHIFT;
}

/* tensor.DMA_PERF[18]: 32-bit array of 18, stride 4 @ offset 0x200 - Tensor DMA adapter counter j (TDMA_PC_*) */
#define SF_TENSOR_DMA_PERF_OFFSET UINT64_C(0x200)
#define SF_TENSOR_DMA_PERF_ADDR UINT64_C(0x150000200)
#define SF_TENSOR_DMA_PERF_WIDTH 32u
#define SF_TENSOR_DMA_PERF_RESET UINT32_C(0x0)
#define SF_TENSOR_DMA_PERF_RW_MASK UINT32_C(0x0)
#define SF_TENSOR_DMA_PERF_COUNT 18u
#define SF_TENSOR_DMA_PERF_STRIDE UINT64_C(4)
SF_REGS_STATIC_ASSERT((SF_TENSOR_DMA_PERF_ADDR % 4u) == 0u, "tensor.DMA_PERF is not naturally aligned");
#define SF_TENSOR_DMA_PERF_VALUE_SHIFT 0u
#define SF_TENSOR_DMA_PERF_VALUE_WIDTH 32u
#define SF_TENSOR_DMA_PERF_VALUE_MASK UINT32_C(0xffffffff)
#define SF_TENSOR_DMA_PERF_VALUE_RESET UINT32_C(0x0)
static inline uint64_t sf_tensor_dma_perf_addr(unsigned i)
{
    if (i >= SF_TENSOR_DMA_PERF_COUNT) { SF_REGS_FAULT(); }
    return SF_TENSOR_DMA_PERF_ADDR + (uint64_t)i * SF_TENSOR_DMA_PERF_STRIDE;
}
static inline uint32_t sf_tensor_dma_perf_read(unsigned i)
{
    return sf_regs_rd32_(sf_tensor_dma_perf_addr(i));
}
static inline uint32_t sf_tensor_dma_perf_get_value(uint32_t reg)
{
    return (reg & SF_TENSOR_DMA_PERF_VALUE_MASK) >> SF_TENSOR_DMA_PERF_VALUE_SHIFT;
}

/* ---------- vector: Vector/DMA command interface (hardware command queue and scheduler) ---------- */
/* region tensor_vector; window 0x150001000 + 0x1000 */

/* vector.ID: 32-bit @ offset 0x0 - ASCII "SFCQ" */
#define SF_VECTOR_ID_OFFSET UINT64_C(0x0)
#define SF_VECTOR_ID_ADDR UINT64_C(0x150001000)
#define SF_VECTOR_ID_WIDTH 32u
#define SF_VECTOR_ID_RESET UINT32_C(0x53464351)
#define SF_VECTOR_ID_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_VECTOR_ID_ADDR % 4u) == 0u, "vector.ID is not naturally aligned");
#define SF_VECTOR_ID_VALUE_SHIFT 0u
#define SF_VECTOR_ID_VALUE_WIDTH 32u
#define SF_VECTOR_ID_VALUE_MASK UINT32_C(0xffffffff)
#define SF_VECTOR_ID_VALUE_RESET UINT32_C(0x53464351)
static inline uint32_t sf_vector_id_read(void)
{
    return sf_regs_rd32_(SF_VECTOR_ID_ADDR);
}
static inline uint32_t sf_vector_id_get_value(uint32_t reg)
{
    return (reg & SF_VECTOR_ID_VALUE_MASK) >> SF_VECTOR_ID_VALUE_SHIFT;
}

/* vector.INFO: 32-bit @ offset 0x4 - Build configuration (from the instantiation parameters) */
#define SF_VECTOR_INFO_OFFSET UINT64_C(0x4)
#define SF_VECTOR_INFO_ADDR UINT64_C(0x150001004)
#define SF_VECTOR_INFO_WIDTH 32u
#define SF_VECTOR_INFO_RESET UINT32_C(0x0)
#define SF_VECTOR_INFO_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_VECTOR_INFO_ADDR % 4u) == 0u, "vector.INFO is not naturally aligned");
#define SF_VECTOR_INFO_ABI_VERSION_SHIFT 0u
#define SF_VECTOR_INFO_ABI_VERSION_WIDTH 4u
#define SF_VECTOR_INFO_ABI_VERSION_MASK UINT32_C(0xf)
#define SF_VECTOR_INFO_ABI_VERSION_RESET UINT32_C(0x0)
#define SF_VECTOR_INFO_QUEUE_DEPTH_SHIFT 8u
#define SF_VECTOR_INFO_QUEUE_DEPTH_WIDTH 8u
#define SF_VECTOR_INFO_QUEUE_DEPTH_MASK UINT32_C(0xff00)
#define SF_VECTOR_INFO_QUEUE_DEPTH_RESET UINT32_C(0x0)
#define SF_VECTOR_INFO_ROB_DEPTH_SHIFT 16u
#define SF_VECTOR_INFO_ROB_DEPTH_WIDTH 8u
#define SF_VECTOR_INFO_ROB_DEPTH_MASK UINT32_C(0xff0000)
#define SF_VECTOR_INFO_ROB_DEPTH_RESET UINT32_C(0x0)
#define SF_VECTOR_INFO_OPSET_FULL_SHIFT 24u
#define SF_VECTOR_INFO_OPSET_FULL_WIDTH 1u
#define SF_VECTOR_INFO_OPSET_FULL_MASK UINT32_C(0x1000000)
#define SF_VECTOR_INFO_OPSET_FULL_RESET UINT32_C(0x0)
#define SF_VECTOR_INFO_OVERLAP_EN_SHIFT 25u
#define SF_VECTOR_INFO_OVERLAP_EN_WIDTH 1u
#define SF_VECTOR_INFO_OVERLAP_EN_MASK UINT32_C(0x2000000)
#define SF_VECTOR_INFO_OVERLAP_EN_RESET UINT32_C(0x0)
#define SF_VECTOR_INFO_PERF_EN_SHIFT 26u
#define SF_VECTOR_INFO_PERF_EN_WIDTH 1u
#define SF_VECTOR_INFO_PERF_EN_MASK UINT32_C(0x4000000)
#define SF_VECTOR_INFO_PERF_EN_RESET UINT32_C(0x0)
static inline uint32_t sf_vector_info_read(void)
{
    return sf_regs_rd32_(SF_VECTOR_INFO_ADDR);
}
static inline uint32_t sf_vector_info_get_abi_version(uint32_t reg)
{
    return (reg & SF_VECTOR_INFO_ABI_VERSION_MASK) >> SF_VECTOR_INFO_ABI_VERSION_SHIFT;
}
static inline uint32_t sf_vector_info_get_queue_depth(uint32_t reg)
{
    return (reg & SF_VECTOR_INFO_QUEUE_DEPTH_MASK) >> SF_VECTOR_INFO_QUEUE_DEPTH_SHIFT;
}
static inline uint32_t sf_vector_info_get_rob_depth(uint32_t reg)
{
    return (reg & SF_VECTOR_INFO_ROB_DEPTH_MASK) >> SF_VECTOR_INFO_ROB_DEPTH_SHIFT;
}
static inline uint32_t sf_vector_info_get_opset_full(uint32_t reg)
{
    return (reg & SF_VECTOR_INFO_OPSET_FULL_MASK) >> SF_VECTOR_INFO_OPSET_FULL_SHIFT;
}
static inline uint32_t sf_vector_info_get_overlap_en(uint32_t reg)
{
    return (reg & SF_VECTOR_INFO_OVERLAP_EN_MASK) >> SF_VECTOR_INFO_OVERLAP_EN_SHIFT;
}
static inline uint32_t sf_vector_info_get_perf_en(uint32_t reg)
{
    return (reg & SF_VECTOR_INFO_PERF_EN_MASK) >> SF_VECTOR_INFO_PERF_EN_SHIFT;
}

/* vector.CTRL: 32-bit @ offset 0x8 - Control */
#define SF_VECTOR_CTRL_OFFSET UINT64_C(0x8)
#define SF_VECTOR_CTRL_ADDR UINT64_C(0x150001008)
#define SF_VECTOR_CTRL_WIDTH 32u
#define SF_VECTOR_CTRL_RESET UINT32_C(0x0)
#define SF_VECTOR_CTRL_RW_MASK UINT32_C(0x1)
SF_REGS_STATIC_ASSERT((SF_VECTOR_CTRL_ADDR % 4u) == 0u, "vector.CTRL is not naturally aligned");
#define SF_VECTOR_CTRL_ERR_CONT_SHIFT 0u
#define SF_VECTOR_CTRL_ERR_CONT_WIDTH 1u
#define SF_VECTOR_CTRL_ERR_CONT_MASK UINT32_C(0x1)
#define SF_VECTOR_CTRL_ERR_CONT_RESET UINT32_C(0x0)
#define SF_VECTOR_CTRL_ERR_CLEAR_SHIFT 1u
#define SF_VECTOR_CTRL_ERR_CLEAR_WIDTH 1u
#define SF_VECTOR_CTRL_ERR_CLEAR_MASK UINT32_C(0x2)
#define SF_VECTOR_CTRL_ERR_CLEAR_RESET UINT32_C(0x0)
#define SF_VECTOR_CTRL_PERF_CLEAR_SHIFT 2u
#define SF_VECTOR_CTRL_PERF_CLEAR_WIDTH 1u
#define SF_VECTOR_CTRL_PERF_CLEAR_MASK UINT32_C(0x4)
#define SF_VECTOR_CTRL_PERF_CLEAR_RESET UINT32_C(0x0)
static inline uint32_t sf_vector_ctrl_read(void)
{
    return sf_regs_rd32_(SF_VECTOR_CTRL_ADDR);
}
static inline void sf_vector_ctrl_write(uint32_t value)
{
    sf_regs_wr32_(SF_VECTOR_CTRL_ADDR, value);
}
static inline uint32_t sf_vector_ctrl_get_err_cont(uint32_t reg)
{
    return (reg & SF_VECTOR_CTRL_ERR_CONT_MASK) >> SF_VECTOR_CTRL_ERR_CONT_SHIFT;
}
static inline uint32_t sf_vector_ctrl_err_cont_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_VECTOR_CTRL_ERR_CONT_SHIFT) & SF_VECTOR_CTRL_ERR_CONT_MASK;
}
/* RMW of rw field ERR_CONT: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_vector_ctrl_set_err_cont(uint32_t value)
{
    uint32_t v = sf_vector_ctrl_read() & SF_VECTOR_CTRL_RW_MASK;
    v = (v & ~SF_VECTOR_CTRL_ERR_CONT_MASK) | sf_vector_ctrl_err_cont_encode(value);
    sf_vector_ctrl_write(v);
}
static inline uint32_t sf_vector_ctrl_err_clear_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_VECTOR_CTRL_ERR_CLEAR_SHIFT) & SF_VECTOR_CTRL_ERR_CLEAR_MASK;
}
/* w1p: write 1 to the chosen bits of ERR_CLEAR (pulse); other rw fields keep their value, other write-one fields get 0. */
static inline void sf_vector_ctrl_pulse_err_clear(uint32_t bits)
{
    uint32_t v = sf_vector_ctrl_read() & SF_VECTOR_CTRL_RW_MASK;
    sf_vector_ctrl_write(v | sf_vector_ctrl_err_clear_encode(bits));
}
static inline uint32_t sf_vector_ctrl_perf_clear_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_VECTOR_CTRL_PERF_CLEAR_SHIFT) & SF_VECTOR_CTRL_PERF_CLEAR_MASK;
}
/* w1p: write 1 to the chosen bits of PERF_CLEAR (pulse); other rw fields keep their value, other write-one fields get 0. */
static inline void sf_vector_ctrl_pulse_perf_clear(uint32_t bits)
{
    uint32_t v = sf_vector_ctrl_read() & SF_VECTOR_CTRL_RW_MASK;
    sf_vector_ctrl_write(v | sf_vector_ctrl_perf_clear_encode(bits));
}

/* vector.STATUS: 32-bit @ offset 0xc - Queue status */
#define SF_VECTOR_STATUS_OFFSET UINT64_C(0xc)
#define SF_VECTOR_STATUS_ADDR UINT64_C(0x15000100c)
#define SF_VECTOR_STATUS_WIDTH 32u
#define SF_VECTOR_STATUS_RESET UINT32_C(0x0)
#define SF_VECTOR_STATUS_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_VECTOR_STATUS_ADDR % 4u) == 0u, "vector.STATUS is not naturally aligned");
#define SF_VECTOR_STATUS_BUSY_SHIFT 0u
#define SF_VECTOR_STATUS_BUSY_WIDTH 1u
#define SF_VECTOR_STATUS_BUSY_MASK UINT32_C(0x1)
#define SF_VECTOR_STATUS_BUSY_RESET UINT32_C(0x0)
#define SF_VECTOR_STATUS_ERR_STICKY_SHIFT 1u
#define SF_VECTOR_STATUS_ERR_STICKY_WIDTH 1u
#define SF_VECTOR_STATUS_ERR_STICKY_MASK UINT32_C(0x2)
#define SF_VECTOR_STATUS_ERR_STICKY_RESET UINT32_C(0x0)
#define SF_VECTOR_STATUS_Q_FULL_SHIFT 2u
#define SF_VECTOR_STATUS_Q_FULL_WIDTH 1u
#define SF_VECTOR_STATUS_Q_FULL_MASK UINT32_C(0x4)
#define SF_VECTOR_STATUS_Q_FULL_RESET UINT32_C(0x0)
#define SF_VECTOR_STATUS_Q_EMPTY_SHIFT 3u
#define SF_VECTOR_STATUS_Q_EMPTY_WIDTH 1u
#define SF_VECTOR_STATUS_Q_EMPTY_MASK UINT32_C(0x8)
#define SF_VECTOR_STATUS_Q_EMPTY_RESET UINT32_C(0x0)
#define SF_VECTOR_STATUS_CPL_VALID_SHIFT 4u
#define SF_VECTOR_STATUS_CPL_VALID_WIDTH 1u
#define SF_VECTOR_STATUS_CPL_VALID_MASK UINT32_C(0x10)
#define SF_VECTOR_STATUS_CPL_VALID_RESET UINT32_C(0x0)
#define SF_VECTOR_STATUS_DMA_DOWN_SHIFT 5u
#define SF_VECTOR_STATUS_DMA_DOWN_WIDTH 1u
#define SF_VECTOR_STATUS_DMA_DOWN_MASK UINT32_C(0x20)
#define SF_VECTOR_STATUS_DMA_DOWN_RESET UINT32_C(0x0)
#define SF_VECTOR_STATUS_VEC_DOWN_SHIFT 6u
#define SF_VECTOR_STATUS_VEC_DOWN_WIDTH 1u
#define SF_VECTOR_STATUS_VEC_DOWN_MASK UINT32_C(0x40)
#define SF_VECTOR_STATUS_VEC_DOWN_RESET UINT32_C(0x0)
#define SF_VECTOR_STATUS_Q_COUNT_SHIFT 8u
#define SF_VECTOR_STATUS_Q_COUNT_WIDTH 8u
#define SF_VECTOR_STATUS_Q_COUNT_MASK UINT32_C(0xff00)
#define SF_VECTOR_STATUS_Q_COUNT_RESET UINT32_C(0x0)
#define SF_VECTOR_STATUS_ROB_COUNT_SHIFT 16u
#define SF_VECTOR_STATUS_ROB_COUNT_WIDTH 8u
#define SF_VECTOR_STATUS_ROB_COUNT_MASK UINT32_C(0xff0000)
#define SF_VECTOR_STATUS_ROB_COUNT_RESET UINT32_C(0x0)
#define SF_VECTOR_STATUS_Q_FREE_SHIFT 24u
#define SF_VECTOR_STATUS_Q_FREE_WIDTH 8u
#define SF_VECTOR_STATUS_Q_FREE_MASK UINT32_C(0xff000000)
#define SF_VECTOR_STATUS_Q_FREE_RESET UINT32_C(0x0)
static inline uint32_t sf_vector_status_read(void)
{
    return sf_regs_rd32_(SF_VECTOR_STATUS_ADDR);
}
static inline uint32_t sf_vector_status_get_busy(uint32_t reg)
{
    return (reg & SF_VECTOR_STATUS_BUSY_MASK) >> SF_VECTOR_STATUS_BUSY_SHIFT;
}
static inline uint32_t sf_vector_status_get_err_sticky(uint32_t reg)
{
    return (reg & SF_VECTOR_STATUS_ERR_STICKY_MASK) >> SF_VECTOR_STATUS_ERR_STICKY_SHIFT;
}
static inline uint32_t sf_vector_status_get_q_full(uint32_t reg)
{
    return (reg & SF_VECTOR_STATUS_Q_FULL_MASK) >> SF_VECTOR_STATUS_Q_FULL_SHIFT;
}
static inline uint32_t sf_vector_status_get_q_empty(uint32_t reg)
{
    return (reg & SF_VECTOR_STATUS_Q_EMPTY_MASK) >> SF_VECTOR_STATUS_Q_EMPTY_SHIFT;
}
static inline uint32_t sf_vector_status_get_cpl_valid(uint32_t reg)
{
    return (reg & SF_VECTOR_STATUS_CPL_VALID_MASK) >> SF_VECTOR_STATUS_CPL_VALID_SHIFT;
}
static inline uint32_t sf_vector_status_get_dma_down(uint32_t reg)
{
    return (reg & SF_VECTOR_STATUS_DMA_DOWN_MASK) >> SF_VECTOR_STATUS_DMA_DOWN_SHIFT;
}
static inline uint32_t sf_vector_status_get_vec_down(uint32_t reg)
{
    return (reg & SF_VECTOR_STATUS_VEC_DOWN_MASK) >> SF_VECTOR_STATUS_VEC_DOWN_SHIFT;
}
static inline uint32_t sf_vector_status_get_q_count(uint32_t reg)
{
    return (reg & SF_VECTOR_STATUS_Q_COUNT_MASK) >> SF_VECTOR_STATUS_Q_COUNT_SHIFT;
}
static inline uint32_t sf_vector_status_get_rob_count(uint32_t reg)
{
    return (reg & SF_VECTOR_STATUS_ROB_COUNT_MASK) >> SF_VECTOR_STATUS_ROB_COUNT_SHIFT;
}
static inline uint32_t sf_vector_status_get_q_free(uint32_t reg)
{
    return (reg & SF_VECTOR_STATUS_Q_FREE_MASK) >> SF_VECTOR_STATUS_Q_FREE_SHIFT;
}

/* vector.INT_ENABLE: 32-bit @ offset 0x10 - Interrupt enables */
#define SF_VECTOR_INT_ENABLE_OFFSET UINT64_C(0x10)
#define SF_VECTOR_INT_ENABLE_ADDR UINT64_C(0x150001010)
#define SF_VECTOR_INT_ENABLE_WIDTH 32u
#define SF_VECTOR_INT_ENABLE_RESET UINT32_C(0x0)
#define SF_VECTOR_INT_ENABLE_RW_MASK UINT32_C(0x3)
SF_REGS_STATIC_ASSERT((SF_VECTOR_INT_ENABLE_ADDR % 4u) == 0u, "vector.INT_ENABLE is not naturally aligned");
#define SF_VECTOR_INT_ENABLE_IRQ_SHIFT 0u
#define SF_VECTOR_INT_ENABLE_IRQ_WIDTH 1u
#define SF_VECTOR_INT_ENABLE_IRQ_MASK UINT32_C(0x1)
#define SF_VECTOR_INT_ENABLE_IRQ_RESET UINT32_C(0x0)
#define SF_VECTOR_INT_ENABLE_ERR_SHIFT 1u
#define SF_VECTOR_INT_ENABLE_ERR_WIDTH 1u
#define SF_VECTOR_INT_ENABLE_ERR_MASK UINT32_C(0x2)
#define SF_VECTOR_INT_ENABLE_ERR_RESET UINT32_C(0x0)
static inline uint32_t sf_vector_int_enable_read(void)
{
    return sf_regs_rd32_(SF_VECTOR_INT_ENABLE_ADDR);
}
static inline void sf_vector_int_enable_write(uint32_t value)
{
    sf_regs_wr32_(SF_VECTOR_INT_ENABLE_ADDR, value);
}
static inline uint32_t sf_vector_int_enable_get_irq(uint32_t reg)
{
    return (reg & SF_VECTOR_INT_ENABLE_IRQ_MASK) >> SF_VECTOR_INT_ENABLE_IRQ_SHIFT;
}
static inline uint32_t sf_vector_int_enable_irq_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_VECTOR_INT_ENABLE_IRQ_SHIFT) & SF_VECTOR_INT_ENABLE_IRQ_MASK;
}
/* RMW of rw field IRQ: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_vector_int_enable_set_irq(uint32_t value)
{
    uint32_t v = sf_vector_int_enable_read() & SF_VECTOR_INT_ENABLE_RW_MASK;
    v = (v & ~SF_VECTOR_INT_ENABLE_IRQ_MASK) | sf_vector_int_enable_irq_encode(value);
    sf_vector_int_enable_write(v);
}
static inline uint32_t sf_vector_int_enable_get_err(uint32_t reg)
{
    return (reg & SF_VECTOR_INT_ENABLE_ERR_MASK) >> SF_VECTOR_INT_ENABLE_ERR_SHIFT;
}
static inline uint32_t sf_vector_int_enable_err_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_VECTOR_INT_ENABLE_ERR_SHIFT) & SF_VECTOR_INT_ENABLE_ERR_MASK;
}
/* RMW of rw field ERR: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_vector_int_enable_set_err(uint32_t value)
{
    uint32_t v = sf_vector_int_enable_read() & SF_VECTOR_INT_ENABLE_RW_MASK;
    v = (v & ~SF_VECTOR_INT_ENABLE_ERR_MASK) | sf_vector_int_enable_err_encode(value);
    sf_vector_int_enable_write(v);
}

/* vector.INT_STATUS: 32-bit @ offset 0x14 - Interrupt status (write 1 to clear; a same-cycle hardware event wins) */
#define SF_VECTOR_INT_STATUS_OFFSET UINT64_C(0x14)
#define SF_VECTOR_INT_STATUS_ADDR UINT64_C(0x150001014)
#define SF_VECTOR_INT_STATUS_WIDTH 32u
#define SF_VECTOR_INT_STATUS_RESET UINT32_C(0x0)
#define SF_VECTOR_INT_STATUS_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_VECTOR_INT_STATUS_ADDR % 4u) == 0u, "vector.INT_STATUS is not naturally aligned");
#define SF_VECTOR_INT_STATUS_IRQ_SHIFT 0u
#define SF_VECTOR_INT_STATUS_IRQ_WIDTH 1u
#define SF_VECTOR_INT_STATUS_IRQ_MASK UINT32_C(0x1)
#define SF_VECTOR_INT_STATUS_IRQ_RESET UINT32_C(0x0)
#define SF_VECTOR_INT_STATUS_ERR_SHIFT 1u
#define SF_VECTOR_INT_STATUS_ERR_WIDTH 1u
#define SF_VECTOR_INT_STATUS_ERR_MASK UINT32_C(0x2)
#define SF_VECTOR_INT_STATUS_ERR_RESET UINT32_C(0x0)
static inline uint32_t sf_vector_int_status_read(void)
{
    return sf_regs_rd32_(SF_VECTOR_INT_STATUS_ADDR);
}
static inline void sf_vector_int_status_write(uint32_t value)
{
    sf_regs_wr32_(SF_VECTOR_INT_STATUS_ADDR, value);
}
static inline uint32_t sf_vector_int_status_get_irq(uint32_t reg)
{
    return (reg & SF_VECTOR_INT_STATUS_IRQ_MASK) >> SF_VECTOR_INT_STATUS_IRQ_SHIFT;
}
static inline uint32_t sf_vector_int_status_irq_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_VECTOR_INT_STATUS_IRQ_SHIFT) & SF_VECTOR_INT_STATUS_IRQ_MASK;
}
/* w1c: write 1 to the chosen bits of IRQ (clear); other rw fields keep their value, other write-one fields get 0. */
static inline void sf_vector_int_status_clear_irq(uint32_t bits)
{
    sf_vector_int_status_write(sf_vector_int_status_irq_encode(bits));
}
static inline uint32_t sf_vector_int_status_get_err(uint32_t reg)
{
    return (reg & SF_VECTOR_INT_STATUS_ERR_MASK) >> SF_VECTOR_INT_STATUS_ERR_SHIFT;
}
static inline uint32_t sf_vector_int_status_err_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_VECTOR_INT_STATUS_ERR_SHIFT) & SF_VECTOR_INT_STATUS_ERR_MASK;
}
/* w1c: write 1 to the chosen bits of ERR (clear); other rw fields keep their value, other write-one fields get 0. */
static inline void sf_vector_int_status_clear_err(uint32_t bits)
{
    sf_vector_int_status_write(sf_vector_int_status_err_encode(bits));
}

/* vector.SUBMITTED: 32-bit @ offset 0x18 - Doorbells accepted since reset (glue counter) */
#define SF_VECTOR_SUBMITTED_OFFSET UINT64_C(0x18)
#define SF_VECTOR_SUBMITTED_ADDR UINT64_C(0x150001018)
#define SF_VECTOR_SUBMITTED_WIDTH 32u
#define SF_VECTOR_SUBMITTED_RESET UINT32_C(0x0)
#define SF_VECTOR_SUBMITTED_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_VECTOR_SUBMITTED_ADDR % 4u) == 0u, "vector.SUBMITTED is not naturally aligned");
#define SF_VECTOR_SUBMITTED_VALUE_SHIFT 0u
#define SF_VECTOR_SUBMITTED_VALUE_WIDTH 32u
#define SF_VECTOR_SUBMITTED_VALUE_MASK UINT32_C(0xffffffff)
#define SF_VECTOR_SUBMITTED_VALUE_RESET UINT32_C(0x0)
static inline uint32_t sf_vector_submitted_read(void)
{
    return sf_regs_rd32_(SF_VECTOR_SUBMITTED_ADDR);
}
static inline uint32_t sf_vector_submitted_get_value(uint32_t reg)
{
    return (reg & SF_VECTOR_SUBMITTED_VALUE_MASK) >> SF_VECTOR_SUBMITTED_VALUE_SHIFT;
}

/* vector.DESC[8]: 32-bit array of 8, stride 4 @ offset 0x20 - Descriptor staging words 0..7 (kept after the doorbell) */
#define SF_VECTOR_DESC_OFFSET UINT64_C(0x20)
#define SF_VECTOR_DESC_ADDR UINT64_C(0x150001020)
#define SF_VECTOR_DESC_WIDTH 32u
#define SF_VECTOR_DESC_RESET UINT32_C(0x0)
#define SF_VECTOR_DESC_RW_MASK UINT32_C(0xffffffff)
#define SF_VECTOR_DESC_COUNT 8u
#define SF_VECTOR_DESC_STRIDE UINT64_C(4)
SF_REGS_STATIC_ASSERT((SF_VECTOR_DESC_ADDR % 4u) == 0u, "vector.DESC is not naturally aligned");
#define SF_VECTOR_DESC_VALUE_SHIFT 0u
#define SF_VECTOR_DESC_VALUE_WIDTH 32u
#define SF_VECTOR_DESC_VALUE_MASK UINT32_C(0xffffffff)
#define SF_VECTOR_DESC_VALUE_RESET UINT32_C(0x0)
static inline uint64_t sf_vector_desc_addr(unsigned i)
{
    if (i >= SF_VECTOR_DESC_COUNT) { SF_REGS_FAULT(); }
    return SF_VECTOR_DESC_ADDR + (uint64_t)i * SF_VECTOR_DESC_STRIDE;
}
static inline uint32_t sf_vector_desc_read(unsigned i)
{
    return sf_regs_rd32_(sf_vector_desc_addr(i));
}
static inline void sf_vector_desc_write(unsigned i, uint32_t value)
{
    sf_regs_wr32_(sf_vector_desc_addr(i), value);
}
static inline uint32_t sf_vector_desc_get_value(uint32_t reg)
{
    return (reg & SF_VECTOR_DESC_VALUE_MASK) >> SF_VECTOR_DESC_VALUE_SHIFT;
}
static inline uint32_t sf_vector_desc_value_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_VECTOR_DESC_VALUE_SHIFT) & SF_VECTOR_DESC_VALUE_MASK;
}
/* RMW of rw field VALUE: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_vector_desc_set_value(unsigned i, uint32_t value)
{
    uint32_t v = sf_vector_desc_read(i) & SF_VECTOR_DESC_RW_MASK;
    v = (v & ~SF_VECTOR_DESC_VALUE_MASK) | sf_vector_desc_value_encode(value);
    sf_vector_desc_write(i, v);
}

/* vector.DOORBELL: 32-bit @ offset 0x40 - Submit the staged descriptor. Refused (TARGET_ERR) while the queue is full; nothing is submitted. */
#define SF_VECTOR_DOORBELL_OFFSET UINT64_C(0x40)
#define SF_VECTOR_DOORBELL_ADDR UINT64_C(0x150001040)
#define SF_VECTOR_DOORBELL_WIDTH 32u
#define SF_VECTOR_DOORBELL_RESET UINT32_C(0x0)
#define SF_VECTOR_DOORBELL_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_VECTOR_DOORBELL_ADDR % 4u) == 0u, "vector.DOORBELL is not naturally aligned");
#define SF_VECTOR_DOORBELL_RING_SHIFT 0u
#define SF_VECTOR_DOORBELL_RING_WIDTH 32u
#define SF_VECTOR_DOORBELL_RING_MASK UINT32_C(0xffffffff)
#define SF_VECTOR_DOORBELL_RING_RESET UINT32_C(0x0)
static inline void sf_vector_doorbell_write(uint32_t value)
{
    sf_regs_wr32_(SF_VECTOR_DOORBELL_ADDR, value);
}
static inline uint32_t sf_vector_doorbell_ring_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_VECTOR_DOORBELL_RING_SHIFT) & SF_VECTOR_DOORBELL_RING_MASK;
}

/* vector.CPL[4]: 32-bit array of 4, stride 4 @ offset 0x50 - Head completion record words 0..3 (0 if there is none) */
#define SF_VECTOR_CPL_OFFSET UINT64_C(0x50)
#define SF_VECTOR_CPL_ADDR UINT64_C(0x150001050)
#define SF_VECTOR_CPL_WIDTH 32u
#define SF_VECTOR_CPL_RESET UINT32_C(0x0)
#define SF_VECTOR_CPL_RW_MASK UINT32_C(0x0)
#define SF_VECTOR_CPL_COUNT 4u
#define SF_VECTOR_CPL_STRIDE UINT64_C(4)
SF_REGS_STATIC_ASSERT((SF_VECTOR_CPL_ADDR % 4u) == 0u, "vector.CPL is not naturally aligned");
#define SF_VECTOR_CPL_VALUE_SHIFT 0u
#define SF_VECTOR_CPL_VALUE_WIDTH 32u
#define SF_VECTOR_CPL_VALUE_MASK UINT32_C(0xffffffff)
#define SF_VECTOR_CPL_VALUE_RESET UINT32_C(0x0)
static inline uint64_t sf_vector_cpl_addr(unsigned i)
{
    if (i >= SF_VECTOR_CPL_COUNT) { SF_REGS_FAULT(); }
    return SF_VECTOR_CPL_ADDR + (uint64_t)i * SF_VECTOR_CPL_STRIDE;
}
static inline uint32_t sf_vector_cpl_read(unsigned i)
{
    return sf_regs_rd32_(sf_vector_cpl_addr(i));
}
static inline uint32_t sf_vector_cpl_get_value(uint32_t reg)
{
    return (reg & SF_VECTOR_CPL_VALUE_MASK) >> SF_VECTOR_CPL_VALUE_SHIFT;
}

/* vector.CPL_POP: 32-bit @ offset 0x60 - Release the head record. Refused (TARGET_ERR) if there is none. */
#define SF_VECTOR_CPL_POP_OFFSET UINT64_C(0x60)
#define SF_VECTOR_CPL_POP_ADDR UINT64_C(0x150001060)
#define SF_VECTOR_CPL_POP_WIDTH 32u
#define SF_VECTOR_CPL_POP_RESET UINT32_C(0x0)
#define SF_VECTOR_CPL_POP_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_VECTOR_CPL_POP_ADDR % 4u) == 0u, "vector.CPL_POP is not naturally aligned");
#define SF_VECTOR_CPL_POP_POP_SHIFT 0u
#define SF_VECTOR_CPL_POP_POP_WIDTH 32u
#define SF_VECTOR_CPL_POP_POP_MASK UINT32_C(0xffffffff)
#define SF_VECTOR_CPL_POP_POP_RESET UINT32_C(0x0)
static inline void sf_vector_cpl_pop_write(uint32_t value)
{
    sf_regs_wr32_(SF_VECTOR_CPL_POP_ADDR, value);
}
static inline uint32_t sf_vector_cpl_pop_pop_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_VECTOR_CPL_POP_POP_SHIFT) & SF_VECTOR_CPL_POP_POP_MASK;
}

/* vector.PERF[17]: 32-bit array of 17, stride 4 @ offset 0x80 - Performance counter i (hpc_cq_pkg PC_*), low 32 bits */
#define SF_VECTOR_PERF_OFFSET UINT64_C(0x80)
#define SF_VECTOR_PERF_ADDR UINT64_C(0x150001080)
#define SF_VECTOR_PERF_WIDTH 32u
#define SF_VECTOR_PERF_RESET UINT32_C(0x0)
#define SF_VECTOR_PERF_RW_MASK UINT32_C(0x0)
#define SF_VECTOR_PERF_COUNT 17u
#define SF_VECTOR_PERF_STRIDE UINT64_C(4)
SF_REGS_STATIC_ASSERT((SF_VECTOR_PERF_ADDR % 4u) == 0u, "vector.PERF is not naturally aligned");
#define SF_VECTOR_PERF_VALUE_SHIFT 0u
#define SF_VECTOR_PERF_VALUE_WIDTH 32u
#define SF_VECTOR_PERF_VALUE_MASK UINT32_C(0xffffffff)
#define SF_VECTOR_PERF_VALUE_RESET UINT32_C(0x0)
static inline uint64_t sf_vector_perf_addr(unsigned i)
{
    if (i >= SF_VECTOR_PERF_COUNT) { SF_REGS_FAULT(); }
    return SF_VECTOR_PERF_ADDR + (uint64_t)i * SF_VECTOR_PERF_STRIDE;
}
static inline uint32_t sf_vector_perf_read(unsigned i)
{
    return sf_regs_rd32_(sf_vector_perf_addr(i));
}
static inline uint32_t sf_vector_perf_get_value(uint32_t reg)
{
    return (reg & SF_VECTOR_PERF_VALUE_MASK) >> SF_VECTOR_PERF_VALUE_SHIFT;
}

/* ---------- perf: Performance counter observation window ---------- */
/* region perf; window 0x170000000 + 0x1000 ; privileged access only */

/* perf.CTRL: 32-bit @ offset 0x0 - Hardware-side counter control */
#define SF_PERF_CTRL_OFFSET UINT64_C(0x0)
#define SF_PERF_CTRL_ADDR UINT64_C(0x170000000)
#define SF_PERF_CTRL_WIDTH 32u
#define SF_PERF_CTRL_RESET UINT32_C(0x0)
#define SF_PERF_CTRL_RW_MASK UINT32_C(0x1)
SF_REGS_STATIC_ASSERT((SF_PERF_CTRL_ADDR % 4u) == 0u, "perf.CTRL is not naturally aligned");
#define SF_PERF_CTRL_FREEZE_SHIFT 0u
#define SF_PERF_CTRL_FREEZE_WIDTH 1u
#define SF_PERF_CTRL_FREEZE_MASK UINT32_C(0x1)
#define SF_PERF_CTRL_FREEZE_RESET UINT32_C(0x0)
#define SF_PERF_CTRL_SNAPSHOT_SHIFT 1u
#define SF_PERF_CTRL_SNAPSHOT_WIDTH 1u
#define SF_PERF_CTRL_SNAPSHOT_MASK UINT32_C(0x2)
#define SF_PERF_CTRL_SNAPSHOT_RESET UINT32_C(0x0)
static inline uint32_t sf_perf_ctrl_read(void)
{
    return sf_regs_rd32_(SF_PERF_CTRL_ADDR);
}
static inline void sf_perf_ctrl_write(uint32_t value)
{
    sf_regs_wr32_(SF_PERF_CTRL_ADDR, value);
}
static inline uint32_t sf_perf_ctrl_get_freeze(uint32_t reg)
{
    return (reg & SF_PERF_CTRL_FREEZE_MASK) >> SF_PERF_CTRL_FREEZE_SHIFT;
}
static inline uint32_t sf_perf_ctrl_freeze_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_PERF_CTRL_FREEZE_SHIFT) & SF_PERF_CTRL_FREEZE_MASK;
}
/* RMW of rw field FREEZE: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_perf_ctrl_set_freeze(uint32_t value)
{
    uint32_t v = sf_perf_ctrl_read() & SF_PERF_CTRL_RW_MASK;
    v = (v & ~SF_PERF_CTRL_FREEZE_MASK) | sf_perf_ctrl_freeze_encode(value);
    sf_perf_ctrl_write(v);
}
static inline uint32_t sf_perf_ctrl_snapshot_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_PERF_CTRL_SNAPSHOT_SHIFT) & SF_PERF_CTRL_SNAPSHOT_MASK;
}
/* w1p: write 1 to the chosen bits of SNAPSHOT (pulse); other rw fields keep their value, other write-one fields get 0. */
static inline void sf_perf_ctrl_pulse_snapshot(uint32_t bits)
{
    uint32_t v = sf_perf_ctrl_read() & SF_PERF_CTRL_RW_MASK;
    sf_perf_ctrl_write(v | sf_perf_ctrl_snapshot_encode(bits));
}

/* perf.STATUS: 32-bit @ offset 0x4 - Counter bank status */
#define SF_PERF_STATUS_OFFSET UINT64_C(0x4)
#define SF_PERF_STATUS_ADDR UINT64_C(0x170000004)
#define SF_PERF_STATUS_WIDTH 32u
#define SF_PERF_STATUS_RESET UINT32_C(0x0)
#define SF_PERF_STATUS_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_PERF_STATUS_ADDR % 4u) == 0u, "perf.STATUS is not naturally aligned");
#define SF_PERF_STATUS_FROZEN_SHIFT 0u
#define SF_PERF_STATUS_FROZEN_WIDTH 1u
#define SF_PERF_STATUS_FROZEN_MASK UINT32_C(0x1)
#define SF_PERF_STATUS_FROZEN_RESET UINT32_C(0x0)
#define SF_PERF_STATUS_IRQ_SHIFT 1u
#define SF_PERF_STATUS_IRQ_WIDTH 1u
#define SF_PERF_STATUS_IRQ_MASK UINT32_C(0x2)
#define SF_PERF_STATUS_IRQ_RESET UINT32_C(0x0)
static inline uint32_t sf_perf_status_read(void)
{
    return sf_regs_rd32_(SF_PERF_STATUS_ADDR);
}
static inline uint32_t sf_perf_status_get_frozen(uint32_t reg)
{
    return (reg & SF_PERF_STATUS_FROZEN_MASK) >> SF_PERF_STATUS_FROZEN_SHIFT;
}
static inline uint32_t sf_perf_status_get_irq(uint32_t reg)
{
    return (reg & SF_PERF_STATUS_IRQ_MASK) >> SF_PERF_STATUS_IRQ_SHIFT;
}

/* perf.CNT[23]: 64-bit array of 23, stride 8 @ offset 0x100 - Live counter i (64-bit): 0 CYCLES, 1 CMD_ACCEPTED, 2 CMD_COMPLETED, 3 VEC_ISSUED, 4 VEC_RETIRED, 5 FLOPS_RETIRED, 6 VEC_STALL, 7 DMA_ACTIVE, 8 DMA_BYTES_RD, 9 DMA_BYTES_WR, 10 SPM_READS, 11 SPM_WRITES, 12 SPM_CONFLICTS, 13 CMDQ_FULL, 14 OUT_BP, 15 HW_ERRORS, 16 VEC_BUSY, 17 VEC_OPND_STARVE, 18 CMD_INFLIGHT_SUM, 19 VEC_CMDQ_OCC_SUM, 20 DMA_OUT_SUM, 21 RED_ADDS, 22 VEC_CMD_COMPLETED */
#define SF_PERF_CNT_OFFSET UINT64_C(0x100)
#define SF_PERF_CNT_ADDR UINT64_C(0x170000100)
#define SF_PERF_CNT_WIDTH 64u
#define SF_PERF_CNT_RESET UINT64_C(0x0)
#define SF_PERF_CNT_RW_MASK UINT64_C(0x0)
#define SF_PERF_CNT_COUNT 23u
#define SF_PERF_CNT_STRIDE UINT64_C(8)
SF_REGS_STATIC_ASSERT((SF_PERF_CNT_ADDR % 8u) == 0u, "perf.CNT is not naturally aligned");
#define SF_PERF_CNT_VALUE_SHIFT 0u
#define SF_PERF_CNT_VALUE_WIDTH 64u
#define SF_PERF_CNT_VALUE_MASK UINT64_C(0xffffffffffffffff)
#define SF_PERF_CNT_VALUE_RESET UINT64_C(0x0)
static inline uint64_t sf_perf_cnt_addr(unsigned i)
{
    if (i >= SF_PERF_CNT_COUNT) { SF_REGS_FAULT(); }
    return SF_PERF_CNT_ADDR + (uint64_t)i * SF_PERF_CNT_STRIDE;
}
static inline uint64_t sf_perf_cnt_read(unsigned i)
{
    return sf_regs_rd64_stable_(sf_perf_cnt_addr(i));
}
static inline uint64_t sf_perf_cnt_get_value(uint64_t reg)
{
    return (reg & SF_PERF_CNT_VALUE_MASK) >> SF_PERF_CNT_VALUE_SHIFT;
}

/* ---------- sysid: System identification and register-map fingerprint ---------- */
/* region sysctl; window 0x180000000 + 0x1000 ; privileged access only */

/* sysid.ID: 32-bit @ offset 0x0 - ASCII "SFLX" */
#define SF_SYSID_ID_OFFSET UINT64_C(0x0)
#define SF_SYSID_ID_ADDR UINT64_C(0x180000000)
#define SF_SYSID_ID_WIDTH 32u
#define SF_SYSID_ID_RESET UINT32_C(0x53464c58)
#define SF_SYSID_ID_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_SYSID_ID_ADDR % 4u) == 0u, "sysid.ID is not naturally aligned");
#define SF_SYSID_ID_VALUE_SHIFT 0u
#define SF_SYSID_ID_VALUE_WIDTH 32u
#define SF_SYSID_ID_VALUE_MASK UINT32_C(0xffffffff)
#define SF_SYSID_ID_VALUE_RESET UINT32_C(0x53464c58)
static inline uint32_t sf_sysid_id_read(void)
{
    return sf_regs_rd32_(SF_SYSID_ID_ADDR);
}
static inline uint32_t sf_sysid_id_get_value(uint32_t reg)
{
    return (reg & SF_SYSID_ID_VALUE_MASK) >> SF_SYSID_ID_VALUE_SHIFT;
}

/* sysid.REGMAP_VERSION: 32-bit @ offset 0x4 - Version of this register map (major.minor) */
#define SF_SYSID_REGMAP_VERSION_OFFSET UINT64_C(0x4)
#define SF_SYSID_REGMAP_VERSION_ADDR UINT64_C(0x180000004)
#define SF_SYSID_REGMAP_VERSION_WIDTH 32u
#define SF_SYSID_REGMAP_VERSION_RESET UINT32_C(0x10000)
#define SF_SYSID_REGMAP_VERSION_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_SYSID_REGMAP_VERSION_ADDR % 4u) == 0u, "sysid.REGMAP_VERSION is not naturally aligned");
#define SF_SYSID_REGMAP_VERSION_MINOR_SHIFT 0u
#define SF_SYSID_REGMAP_VERSION_MINOR_WIDTH 16u
#define SF_SYSID_REGMAP_VERSION_MINOR_MASK UINT32_C(0xffff)
#define SF_SYSID_REGMAP_VERSION_MINOR_RESET UINT32_C(0x0)
#define SF_SYSID_REGMAP_VERSION_MAJOR_SHIFT 16u
#define SF_SYSID_REGMAP_VERSION_MAJOR_WIDTH 16u
#define SF_SYSID_REGMAP_VERSION_MAJOR_MASK UINT32_C(0xffff0000)
#define SF_SYSID_REGMAP_VERSION_MAJOR_RESET UINT32_C(0x1)
static inline uint32_t sf_sysid_regmap_version_read(void)
{
    return sf_regs_rd32_(SF_SYSID_REGMAP_VERSION_ADDR);
}
static inline uint32_t sf_sysid_regmap_version_get_minor(uint32_t reg)
{
    return (reg & SF_SYSID_REGMAP_VERSION_MINOR_MASK) >> SF_SYSID_REGMAP_VERSION_MINOR_SHIFT;
}
static inline uint32_t sf_sysid_regmap_version_get_major(uint32_t reg)
{
    return (reg & SF_SYSID_REGMAP_VERSION_MAJOR_MASK) >> SF_SYSID_REGMAP_VERSION_MAJOR_SHIFT;
}

/* sysid.ALP_VERSION: 32-bit @ offset 0x8 - Albion Link Protocol version implemented by the register bank (SF_ALP_VERSION_*) */
#define SF_SYSID_ALP_VERSION_OFFSET UINT64_C(0x8)
#define SF_SYSID_ALP_VERSION_ADDR UINT64_C(0x180000008)
#define SF_SYSID_ALP_VERSION_WIDTH 32u
#define SF_SYSID_ALP_VERSION_RESET UINT32_C(0x1)
#define SF_SYSID_ALP_VERSION_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_SYSID_ALP_VERSION_ADDR % 4u) == 0u, "sysid.ALP_VERSION is not naturally aligned");
#define SF_SYSID_ALP_VERSION_MAJOR_SHIFT 0u
#define SF_SYSID_ALP_VERSION_MAJOR_WIDTH 8u
#define SF_SYSID_ALP_VERSION_MAJOR_MASK UINT32_C(0xff)
#define SF_SYSID_ALP_VERSION_MAJOR_RESET UINT32_C(0x1)
#define SF_SYSID_ALP_VERSION_MINOR_SHIFT 8u
#define SF_SYSID_ALP_VERSION_MINOR_WIDTH 8u
#define SF_SYSID_ALP_VERSION_MINOR_MASK UINT32_C(0xff00)
#define SF_SYSID_ALP_VERSION_MINOR_RESET UINT32_C(0x0)
static inline uint32_t sf_sysid_alp_version_read(void)
{
    return sf_regs_rd32_(SF_SYSID_ALP_VERSION_ADDR);
}
static inline uint32_t sf_sysid_alp_version_get_major(uint32_t reg)
{
    return (reg & SF_SYSID_ALP_VERSION_MAJOR_MASK) >> SF_SYSID_ALP_VERSION_MAJOR_SHIFT;
}
static inline uint32_t sf_sysid_alp_version_get_minor(uint32_t reg)
{
    return (reg & SF_SYSID_ALP_VERSION_MINOR_MASK) >> SF_SYSID_ALP_VERSION_MINOR_SHIFT;
}

/* sysid.LIB_VERSION: 32-bit @ offset 0xc - AlbionCore library version the RTL was generated against (SF_ALBION_LIB_*) */
#define SF_SYSID_LIB_VERSION_OFFSET UINT64_C(0xc)
#define SF_SYSID_LIB_VERSION_ADDR UINT64_C(0x18000000c)
#define SF_SYSID_LIB_VERSION_WIDTH 32u
#define SF_SYSID_LIB_VERSION_RESET UINT32_C(0x100)
#define SF_SYSID_LIB_VERSION_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_SYSID_LIB_VERSION_ADDR % 4u) == 0u, "sysid.LIB_VERSION is not naturally aligned");
#define SF_SYSID_LIB_VERSION_MAJOR_SHIFT 0u
#define SF_SYSID_LIB_VERSION_MAJOR_WIDTH 8u
#define SF_SYSID_LIB_VERSION_MAJOR_MASK UINT32_C(0xff)
#define SF_SYSID_LIB_VERSION_MAJOR_RESET UINT32_C(0x0)
#define SF_SYSID_LIB_VERSION_MINOR_SHIFT 8u
#define SF_SYSID_LIB_VERSION_MINOR_WIDTH 8u
#define SF_SYSID_LIB_VERSION_MINOR_MASK UINT32_C(0xff00)
#define SF_SYSID_LIB_VERSION_MINOR_RESET UINT32_C(0x1)
#define SF_SYSID_LIB_VERSION_PATCH_SHIFT 16u
#define SF_SYSID_LIB_VERSION_PATCH_WIDTH 8u
#define SF_SYSID_LIB_VERSION_PATCH_MASK UINT32_C(0xff0000)
#define SF_SYSID_LIB_VERSION_PATCH_RESET UINT32_C(0x0)
static inline uint32_t sf_sysid_lib_version_read(void)
{
    return sf_regs_rd32_(SF_SYSID_LIB_VERSION_ADDR);
}
static inline uint32_t sf_sysid_lib_version_get_major(uint32_t reg)
{
    return (reg & SF_SYSID_LIB_VERSION_MAJOR_MASK) >> SF_SYSID_LIB_VERSION_MAJOR_SHIFT;
}
static inline uint32_t sf_sysid_lib_version_get_minor(uint32_t reg)
{
    return (reg & SF_SYSID_LIB_VERSION_MINOR_MASK) >> SF_SYSID_LIB_VERSION_MINOR_SHIFT;
}
static inline uint32_t sf_sysid_lib_version_get_patch(uint32_t reg)
{
    return (reg & SF_SYSID_LIB_VERSION_PATCH_MASK) >> SF_SYSID_LIB_VERSION_PATCH_SHIFT;
}

/* sysid.ALP_CAPS: 64-bit @ offset 0x10 - ALP capability word of this link target, laid out as sf_caps_t. MAX_OUTSTANDING is the capacity of sf_reg_interface (2: it accepts a request in the cycle its predecessor's response leaves); FEATURES is READ|WRITE (no atomics, no out-of-order, no ECC). */
#define SF_SYSID_ALP_CAPS_OFFSET UINT64_C(0x10)
#define SF_SYSID_ALP_CAPS_ADDR UINT64_C(0x180000010)
#define SF_SYSID_ALP_CAPS_WIDTH 64u
#define SF_SYSID_ALP_CAPS_RESET UINT64_C(0x1040488000020003)
#define SF_SYSID_ALP_CAPS_RW_MASK UINT64_C(0x0)
SF_REGS_STATIC_ASSERT((SF_SYSID_ALP_CAPS_ADDR % 8u) == 0u, "sysid.ALP_CAPS is not naturally aligned");
#define SF_SYSID_ALP_CAPS_FEATURES_SHIFT 0u
#define SF_SYSID_ALP_CAPS_FEATURES_WIDTH 16u
#define SF_SYSID_ALP_CAPS_FEATURES_MASK UINT64_C(0xffff)
#define SF_SYSID_ALP_CAPS_FEATURES_RESET UINT64_C(0x3)
#define SF_SYSID_ALP_CAPS_MAX_OUTSTANDING_SHIFT 16u
#define SF_SYSID_ALP_CAPS_MAX_OUTSTANDING_WIDTH 16u
#define SF_SYSID_ALP_CAPS_MAX_OUTSTANDING_MASK UINT64_C(0xffff0000)
#define SF_SYSID_ALP_CAPS_MAX_OUTSTANDING_RESET UINT64_C(0x2)
#define SF_SYSID_ALP_CAPS_RSVD_SHIFT 32u
#define SF_SYSID_ALP_CAPS_RSVD_WIDTH 4u
#define SF_SYSID_ALP_CAPS_RSVD_MASK UINT64_C(0xf00000000)
#define SF_SYSID_ALP_CAPS_RSVD_RESET UINT64_C(0x0)
#define SF_SYSID_ALP_CAPS_DOM_W_SHIFT 36u
#define SF_SYSID_ALP_CAPS_DOM_W_WIDTH 4u
#define SF_SYSID_ALP_CAPS_DOM_W_MASK UINT64_C(0xf000000000)
#define SF_SYSID_ALP_CAPS_DOM_W_RESET UINT64_C(0x8)
#define SF_SYSID_ALP_CAPS_TAG_W_SHIFT 40u
#define SF_SYSID_ALP_CAPS_TAG_W_WIDTH 4u
#define SF_SYSID_ALP_CAPS_TAG_W_MASK UINT64_C(0xf0000000000)
#define SF_SYSID_ALP_CAPS_TAG_W_RESET UINT64_C(0x8)
#define SF_SYSID_ALP_CAPS_DATA_BYTES_LOG2_SHIFT 44u
#define SF_SYSID_ALP_CAPS_DATA_BYTES_LOG2_WIDTH 4u
#define SF_SYSID_ALP_CAPS_DATA_BYTES_LOG2_MASK UINT64_C(0xf00000000000)
#define SF_SYSID_ALP_CAPS_DATA_BYTES_LOG2_RESET UINT64_C(0x4)
#define SF_SYSID_ALP_CAPS_ADDR_W_SHIFT 48u
#define SF_SYSID_ALP_CAPS_ADDR_W_WIDTH 8u
#define SF_SYSID_ALP_CAPS_ADDR_W_MASK UINT64_C(0xff000000000000)
#define SF_SYSID_ALP_CAPS_ADDR_W_RESET UINT64_C(0x40)
#define SF_SYSID_ALP_CAPS_PROTO_MINOR_SHIFT 56u
#define SF_SYSID_ALP_CAPS_PROTO_MINOR_WIDTH 4u
#define SF_SYSID_ALP_CAPS_PROTO_MINOR_MASK UINT64_C(0xf00000000000000)
#define SF_SYSID_ALP_CAPS_PROTO_MINOR_RESET UINT64_C(0x0)
#define SF_SYSID_ALP_CAPS_PROTO_MAJOR_SHIFT 60u
#define SF_SYSID_ALP_CAPS_PROTO_MAJOR_WIDTH 4u
#define SF_SYSID_ALP_CAPS_PROTO_MAJOR_MASK UINT64_C(0xf000000000000000)
#define SF_SYSID_ALP_CAPS_PROTO_MAJOR_RESET UINT64_C(0x1)
static inline uint64_t sf_sysid_alp_caps_read(void)
{
    return sf_regs_rd64_stable_(SF_SYSID_ALP_CAPS_ADDR);
}
static inline uint64_t sf_sysid_alp_caps_get_features(uint64_t reg)
{
    return (reg & SF_SYSID_ALP_CAPS_FEATURES_MASK) >> SF_SYSID_ALP_CAPS_FEATURES_SHIFT;
}
static inline uint64_t sf_sysid_alp_caps_get_max_outstanding(uint64_t reg)
{
    return (reg & SF_SYSID_ALP_CAPS_MAX_OUTSTANDING_MASK) >> SF_SYSID_ALP_CAPS_MAX_OUTSTANDING_SHIFT;
}
static inline uint64_t sf_sysid_alp_caps_get_rsvd(uint64_t reg)
{
    return (reg & SF_SYSID_ALP_CAPS_RSVD_MASK) >> SF_SYSID_ALP_CAPS_RSVD_SHIFT;
}
static inline uint64_t sf_sysid_alp_caps_get_dom_w(uint64_t reg)
{
    return (reg & SF_SYSID_ALP_CAPS_DOM_W_MASK) >> SF_SYSID_ALP_CAPS_DOM_W_SHIFT;
}
static inline uint64_t sf_sysid_alp_caps_get_tag_w(uint64_t reg)
{
    return (reg & SF_SYSID_ALP_CAPS_TAG_W_MASK) >> SF_SYSID_ALP_CAPS_TAG_W_SHIFT;
}
static inline uint64_t sf_sysid_alp_caps_get_data_bytes_log2(uint64_t reg)
{
    return (reg & SF_SYSID_ALP_CAPS_DATA_BYTES_LOG2_MASK) >> SF_SYSID_ALP_CAPS_DATA_BYTES_LOG2_SHIFT;
}
static inline uint64_t sf_sysid_alp_caps_get_addr_w(uint64_t reg)
{
    return (reg & SF_SYSID_ALP_CAPS_ADDR_W_MASK) >> SF_SYSID_ALP_CAPS_ADDR_W_SHIFT;
}
static inline uint64_t sf_sysid_alp_caps_get_proto_minor(uint64_t reg)
{
    return (reg & SF_SYSID_ALP_CAPS_PROTO_MINOR_MASK) >> SF_SYSID_ALP_CAPS_PROTO_MINOR_SHIFT;
}
static inline uint64_t sf_sysid_alp_caps_get_proto_major(uint64_t reg)
{
    return (reg & SF_SYSID_ALP_CAPS_PROTO_MAJOR_MASK) >> SF_SYSID_ALP_CAPS_PROTO_MAJOR_SHIFT;
}

/* sysid.REGMAP_HASH: 64-bit @ offset 0x18 - First 8 bytes of the SHA-256 semantic hash of the register definition (addresses, widths, access types, reset values, hardware options). Firmware compares it with SF_REGS_MAP_HASH. */
#define SF_SYSID_REGMAP_HASH_OFFSET UINT64_C(0x18)
#define SF_SYSID_REGMAP_HASH_ADDR UINT64_C(0x180000018)
#define SF_SYSID_REGMAP_HASH_WIDTH 64u
#define SF_SYSID_REGMAP_HASH_RESET UINT64_C(0x99481283139d2dc0)
#define SF_SYSID_REGMAP_HASH_RW_MASK UINT64_C(0x0)
SF_REGS_STATIC_ASSERT((SF_SYSID_REGMAP_HASH_ADDR % 8u) == 0u, "sysid.REGMAP_HASH is not naturally aligned");
#define SF_SYSID_REGMAP_HASH_VALUE_SHIFT 0u
#define SF_SYSID_REGMAP_HASH_VALUE_WIDTH 64u
#define SF_SYSID_REGMAP_HASH_VALUE_MASK UINT64_C(0xffffffffffffffff)
#define SF_SYSID_REGMAP_HASH_VALUE_RESET UINT64_C(0x99481283139d2dc0)
static inline uint64_t sf_sysid_regmap_hash_read(void)
{
    return sf_regs_rd64_stable_(SF_SYSID_REGMAP_HASH_ADDR);
}
static inline uint64_t sf_sysid_regmap_hash_get_value(uint64_t reg)
{
    return (reg & SF_SYSID_REGMAP_HASH_VALUE_MASK) >> SF_SYSID_REGMAP_HASH_VALUE_SHIFT;
}

/* sysid.BUILD_ID: 32-bit @ offset 0x20 - Build identifier supplied by the integrator (for example a source-control revision) */
#define SF_SYSID_BUILD_ID_OFFSET UINT64_C(0x20)
#define SF_SYSID_BUILD_ID_ADDR UINT64_C(0x180000020)
#define SF_SYSID_BUILD_ID_WIDTH 32u
#define SF_SYSID_BUILD_ID_RESET UINT32_C(0x0)
#define SF_SYSID_BUILD_ID_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_SYSID_BUILD_ID_ADDR % 4u) == 0u, "sysid.BUILD_ID is not naturally aligned");
#define SF_SYSID_BUILD_ID_VALUE_SHIFT 0u
#define SF_SYSID_BUILD_ID_VALUE_WIDTH 32u
#define SF_SYSID_BUILD_ID_VALUE_MASK UINT32_C(0xffffffff)
#define SF_SYSID_BUILD_ID_VALUE_RESET UINT32_C(0x0)
static inline uint32_t sf_sysid_build_id_read(void)
{
    return sf_regs_rd32_(SF_SYSID_BUILD_ID_ADDR);
}
static inline uint32_t sf_sysid_build_id_get_value(uint32_t reg)
{
    return (reg & SF_SYSID_BUILD_ID_VALUE_MASK) >> SF_SYSID_BUILD_ID_VALUE_SHIFT;
}

/* ---------- intc: Interrupt controller (16 level sources, 7 priority levels, threshold, claim) ---------- */
/* region sysctl; window 0x180001000 + 0x1000 ; privileged access only */

/* intc.PENDING: 32-bit @ offset 0x0 - Live source levels OR software-pending bits */
#define SF_INTC_PENDING_OFFSET UINT64_C(0x0)
#define SF_INTC_PENDING_ADDR UINT64_C(0x180001000)
#define SF_INTC_PENDING_WIDTH 32u
#define SF_INTC_PENDING_RESET UINT32_C(0x0)
#define SF_INTC_PENDING_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_INTC_PENDING_ADDR % 4u) == 0u, "intc.PENDING is not naturally aligned");
#define SF_INTC_PENDING_SOURCES_SHIFT 0u
#define SF_INTC_PENDING_SOURCES_WIDTH 16u
#define SF_INTC_PENDING_SOURCES_MASK UINT32_C(0xffff)
#define SF_INTC_PENDING_SOURCES_RESET UINT32_C(0x0)
static inline uint32_t sf_intc_pending_read(void)
{
    return sf_regs_rd32_(SF_INTC_PENDING_ADDR);
}
static inline uint32_t sf_intc_pending_get_sources(uint32_t reg)
{
    return (reg & SF_INTC_PENDING_SOURCES_MASK) >> SF_INTC_PENDING_SOURCES_SHIFT;
}

/* intc.ENABLE: 32-bit @ offset 0x4 - Per-source interrupt enable */
#define SF_INTC_ENABLE_OFFSET UINT64_C(0x4)
#define SF_INTC_ENABLE_ADDR UINT64_C(0x180001004)
#define SF_INTC_ENABLE_WIDTH 32u
#define SF_INTC_ENABLE_RESET UINT32_C(0x0)
#define SF_INTC_ENABLE_RW_MASK UINT32_C(0xffff)
SF_REGS_STATIC_ASSERT((SF_INTC_ENABLE_ADDR % 4u) == 0u, "intc.ENABLE is not naturally aligned");
#define SF_INTC_ENABLE_EN_SHIFT 0u
#define SF_INTC_ENABLE_EN_WIDTH 16u
#define SF_INTC_ENABLE_EN_MASK UINT32_C(0xffff)
#define SF_INTC_ENABLE_EN_RESET UINT32_C(0x0)
static inline uint32_t sf_intc_enable_read(void)
{
    return sf_regs_rd32_(SF_INTC_ENABLE_ADDR);
}
static inline void sf_intc_enable_write(uint32_t value)
{
    sf_regs_wr32_(SF_INTC_ENABLE_ADDR, value);
}
static inline uint32_t sf_intc_enable_get_en(uint32_t reg)
{
    return (reg & SF_INTC_ENABLE_EN_MASK) >> SF_INTC_ENABLE_EN_SHIFT;
}
static inline uint32_t sf_intc_enable_en_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_INTC_ENABLE_EN_SHIFT) & SF_INTC_ENABLE_EN_MASK;
}
/* RMW of rw field EN: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_intc_enable_set_en(uint32_t value)
{
    uint32_t v = sf_intc_enable_read() & SF_INTC_ENABLE_RW_MASK;
    v = (v & ~SF_INTC_ENABLE_EN_MASK) | sf_intc_enable_en_encode(value);
    sf_intc_enable_write(v);
}

/* intc.CLAIM: 32-bit @ offset 0x8 - Highest-priority active source (lowest index wins ties); reading has no side effect */
#define SF_INTC_CLAIM_OFFSET UINT64_C(0x8)
#define SF_INTC_CLAIM_ADDR UINT64_C(0x180001008)
#define SF_INTC_CLAIM_WIDTH 32u
#define SF_INTC_CLAIM_RESET UINT32_C(0x0)
#define SF_INTC_CLAIM_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_INTC_CLAIM_ADDR % 4u) == 0u, "intc.CLAIM is not naturally aligned");
#define SF_INTC_CLAIM_ID_SHIFT 0u
#define SF_INTC_CLAIM_ID_WIDTH 8u
#define SF_INTC_CLAIM_ID_MASK UINT32_C(0xff)
#define SF_INTC_CLAIM_ID_RESET UINT32_C(0x0)
static inline uint32_t sf_intc_claim_read(void)
{
    return sf_regs_rd32_(SF_INTC_CLAIM_ADDR);
}
static inline uint32_t sf_intc_claim_get_id(uint32_t reg)
{
    return (reg & SF_INTC_CLAIM_ID_MASK) >> SF_INTC_CLAIM_ID_SHIFT;
}

/* intc.SWPEND: 32-bit @ offset 0xc - Software-set pending bits (software interrupts per source) */
#define SF_INTC_SWPEND_OFFSET UINT64_C(0xc)
#define SF_INTC_SWPEND_ADDR UINT64_C(0x18000100c)
#define SF_INTC_SWPEND_WIDTH 32u
#define SF_INTC_SWPEND_RESET UINT32_C(0x0)
#define SF_INTC_SWPEND_RW_MASK UINT32_C(0xffff)
SF_REGS_STATIC_ASSERT((SF_INTC_SWPEND_ADDR % 4u) == 0u, "intc.SWPEND is not naturally aligned");
#define SF_INTC_SWPEND_SW_SHIFT 0u
#define SF_INTC_SWPEND_SW_WIDTH 16u
#define SF_INTC_SWPEND_SW_MASK UINT32_C(0xffff)
#define SF_INTC_SWPEND_SW_RESET UINT32_C(0x0)
static inline uint32_t sf_intc_swpend_read(void)
{
    return sf_regs_rd32_(SF_INTC_SWPEND_ADDR);
}
static inline void sf_intc_swpend_write(uint32_t value)
{
    sf_regs_wr32_(SF_INTC_SWPEND_ADDR, value);
}
static inline uint32_t sf_intc_swpend_get_sw(uint32_t reg)
{
    return (reg & SF_INTC_SWPEND_SW_MASK) >> SF_INTC_SWPEND_SW_SHIFT;
}
static inline uint32_t sf_intc_swpend_sw_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_INTC_SWPEND_SW_SHIFT) & SF_INTC_SWPEND_SW_MASK;
}
/* RMW of rw field SW: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_intc_swpend_set_sw(uint32_t value)
{
    uint32_t v = sf_intc_swpend_read() & SF_INTC_SWPEND_RW_MASK;
    v = (v & ~SF_INTC_SWPEND_SW_MASK) | sf_intc_swpend_sw_encode(value);
    sf_intc_swpend_write(v);
}

/* intc.THRESHOLD: 32-bit @ offset 0x10 - Only priorities greater than LEVEL interrupt */
#define SF_INTC_THRESHOLD_OFFSET UINT64_C(0x10)
#define SF_INTC_THRESHOLD_ADDR UINT64_C(0x180001010)
#define SF_INTC_THRESHOLD_WIDTH 32u
#define SF_INTC_THRESHOLD_RESET UINT32_C(0x0)
#define SF_INTC_THRESHOLD_RW_MASK UINT32_C(0x7)
SF_REGS_STATIC_ASSERT((SF_INTC_THRESHOLD_ADDR % 4u) == 0u, "intc.THRESHOLD is not naturally aligned");
#define SF_INTC_THRESHOLD_LEVEL_SHIFT 0u
#define SF_INTC_THRESHOLD_LEVEL_WIDTH 3u
#define SF_INTC_THRESHOLD_LEVEL_MASK UINT32_C(0x7)
#define SF_INTC_THRESHOLD_LEVEL_RESET UINT32_C(0x0)
static inline uint32_t sf_intc_threshold_read(void)
{
    return sf_regs_rd32_(SF_INTC_THRESHOLD_ADDR);
}
static inline void sf_intc_threshold_write(uint32_t value)
{
    sf_regs_wr32_(SF_INTC_THRESHOLD_ADDR, value);
}
static inline uint32_t sf_intc_threshold_get_level(uint32_t reg)
{
    return (reg & SF_INTC_THRESHOLD_LEVEL_MASK) >> SF_INTC_THRESHOLD_LEVEL_SHIFT;
}
static inline uint32_t sf_intc_threshold_level_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_INTC_THRESHOLD_LEVEL_SHIFT) & SF_INTC_THRESHOLD_LEVEL_MASK;
}
/* RMW of rw field LEVEL: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_intc_threshold_set_level(uint32_t value)
{
    uint32_t v = sf_intc_threshold_read() & SF_INTC_THRESHOLD_RW_MASK;
    v = (v & ~SF_INTC_THRESHOLD_LEVEL_MASK) | sf_intc_threshold_level_encode(value);
    sf_intc_threshold_write(v);
}

/* intc.ACTIVE: 32-bit @ offset 0x14 - Pending and enabled and priority above threshold */
#define SF_INTC_ACTIVE_OFFSET UINT64_C(0x14)
#define SF_INTC_ACTIVE_ADDR UINT64_C(0x180001014)
#define SF_INTC_ACTIVE_WIDTH 32u
#define SF_INTC_ACTIVE_RESET UINT32_C(0x0)
#define SF_INTC_ACTIVE_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_INTC_ACTIVE_ADDR % 4u) == 0u, "intc.ACTIVE is not naturally aligned");
#define SF_INTC_ACTIVE_ACT_SHIFT 0u
#define SF_INTC_ACTIVE_ACT_WIDTH 16u
#define SF_INTC_ACTIVE_ACT_MASK UINT32_C(0xffff)
#define SF_INTC_ACTIVE_ACT_RESET UINT32_C(0x0)
static inline uint32_t sf_intc_active_read(void)
{
    return sf_regs_rd32_(SF_INTC_ACTIVE_ADDR);
}
static inline uint32_t sf_intc_active_get_act(uint32_t reg)
{
    return (reg & SF_INTC_ACTIVE_ACT_MASK) >> SF_INTC_ACTIVE_ACT_SHIFT;
}

/* intc.PRIO0: 32-bit @ offset 0x20 - Priority of sources 0..7, 3 bits each in a 4-bit nibble (0 = never) */
#define SF_INTC_PRIO0_OFFSET UINT64_C(0x20)
#define SF_INTC_PRIO0_ADDR UINT64_C(0x180001020)
#define SF_INTC_PRIO0_WIDTH 32u
#define SF_INTC_PRIO0_RESET UINT32_C(0x11111111)
#define SF_INTC_PRIO0_RW_MASK UINT32_C(0x77777777)
SF_REGS_STATIC_ASSERT((SF_INTC_PRIO0_ADDR % 4u) == 0u, "intc.PRIO0 is not naturally aligned");
#define SF_INTC_PRIO0_SRC0_SHIFT 0u
#define SF_INTC_PRIO0_SRC0_WIDTH 3u
#define SF_INTC_PRIO0_SRC0_MASK UINT32_C(0x7)
#define SF_INTC_PRIO0_SRC0_RESET UINT32_C(0x1)
#define SF_INTC_PRIO0_SRC1_SHIFT 4u
#define SF_INTC_PRIO0_SRC1_WIDTH 3u
#define SF_INTC_PRIO0_SRC1_MASK UINT32_C(0x70)
#define SF_INTC_PRIO0_SRC1_RESET UINT32_C(0x1)
#define SF_INTC_PRIO0_SRC2_SHIFT 8u
#define SF_INTC_PRIO0_SRC2_WIDTH 3u
#define SF_INTC_PRIO0_SRC2_MASK UINT32_C(0x700)
#define SF_INTC_PRIO0_SRC2_RESET UINT32_C(0x1)
#define SF_INTC_PRIO0_SRC3_SHIFT 12u
#define SF_INTC_PRIO0_SRC3_WIDTH 3u
#define SF_INTC_PRIO0_SRC3_MASK UINT32_C(0x7000)
#define SF_INTC_PRIO0_SRC3_RESET UINT32_C(0x1)
#define SF_INTC_PRIO0_SRC4_SHIFT 16u
#define SF_INTC_PRIO0_SRC4_WIDTH 3u
#define SF_INTC_PRIO0_SRC4_MASK UINT32_C(0x70000)
#define SF_INTC_PRIO0_SRC4_RESET UINT32_C(0x1)
#define SF_INTC_PRIO0_SRC5_SHIFT 20u
#define SF_INTC_PRIO0_SRC5_WIDTH 3u
#define SF_INTC_PRIO0_SRC5_MASK UINT32_C(0x700000)
#define SF_INTC_PRIO0_SRC5_RESET UINT32_C(0x1)
#define SF_INTC_PRIO0_SRC6_SHIFT 24u
#define SF_INTC_PRIO0_SRC6_WIDTH 3u
#define SF_INTC_PRIO0_SRC6_MASK UINT32_C(0x7000000)
#define SF_INTC_PRIO0_SRC6_RESET UINT32_C(0x1)
#define SF_INTC_PRIO0_SRC7_SHIFT 28u
#define SF_INTC_PRIO0_SRC7_WIDTH 3u
#define SF_INTC_PRIO0_SRC7_MASK UINT32_C(0x70000000)
#define SF_INTC_PRIO0_SRC7_RESET UINT32_C(0x1)
static inline uint32_t sf_intc_prio0_read(void)
{
    return sf_regs_rd32_(SF_INTC_PRIO0_ADDR);
}
static inline void sf_intc_prio0_write(uint32_t value)
{
    sf_regs_wr32_(SF_INTC_PRIO0_ADDR, value);
}
static inline uint32_t sf_intc_prio0_get_src0(uint32_t reg)
{
    return (reg & SF_INTC_PRIO0_SRC0_MASK) >> SF_INTC_PRIO0_SRC0_SHIFT;
}
static inline uint32_t sf_intc_prio0_src0_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_INTC_PRIO0_SRC0_SHIFT) & SF_INTC_PRIO0_SRC0_MASK;
}
/* RMW of rw field SRC0: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_intc_prio0_set_src0(uint32_t value)
{
    uint32_t v = sf_intc_prio0_read() & SF_INTC_PRIO0_RW_MASK;
    v = (v & ~SF_INTC_PRIO0_SRC0_MASK) | sf_intc_prio0_src0_encode(value);
    sf_intc_prio0_write(v);
}
static inline uint32_t sf_intc_prio0_get_src1(uint32_t reg)
{
    return (reg & SF_INTC_PRIO0_SRC1_MASK) >> SF_INTC_PRIO0_SRC1_SHIFT;
}
static inline uint32_t sf_intc_prio0_src1_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_INTC_PRIO0_SRC1_SHIFT) & SF_INTC_PRIO0_SRC1_MASK;
}
/* RMW of rw field SRC1: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_intc_prio0_set_src1(uint32_t value)
{
    uint32_t v = sf_intc_prio0_read() & SF_INTC_PRIO0_RW_MASK;
    v = (v & ~SF_INTC_PRIO0_SRC1_MASK) | sf_intc_prio0_src1_encode(value);
    sf_intc_prio0_write(v);
}
static inline uint32_t sf_intc_prio0_get_src2(uint32_t reg)
{
    return (reg & SF_INTC_PRIO0_SRC2_MASK) >> SF_INTC_PRIO0_SRC2_SHIFT;
}
static inline uint32_t sf_intc_prio0_src2_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_INTC_PRIO0_SRC2_SHIFT) & SF_INTC_PRIO0_SRC2_MASK;
}
/* RMW of rw field SRC2: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_intc_prio0_set_src2(uint32_t value)
{
    uint32_t v = sf_intc_prio0_read() & SF_INTC_PRIO0_RW_MASK;
    v = (v & ~SF_INTC_PRIO0_SRC2_MASK) | sf_intc_prio0_src2_encode(value);
    sf_intc_prio0_write(v);
}
static inline uint32_t sf_intc_prio0_get_src3(uint32_t reg)
{
    return (reg & SF_INTC_PRIO0_SRC3_MASK) >> SF_INTC_PRIO0_SRC3_SHIFT;
}
static inline uint32_t sf_intc_prio0_src3_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_INTC_PRIO0_SRC3_SHIFT) & SF_INTC_PRIO0_SRC3_MASK;
}
/* RMW of rw field SRC3: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_intc_prio0_set_src3(uint32_t value)
{
    uint32_t v = sf_intc_prio0_read() & SF_INTC_PRIO0_RW_MASK;
    v = (v & ~SF_INTC_PRIO0_SRC3_MASK) | sf_intc_prio0_src3_encode(value);
    sf_intc_prio0_write(v);
}
static inline uint32_t sf_intc_prio0_get_src4(uint32_t reg)
{
    return (reg & SF_INTC_PRIO0_SRC4_MASK) >> SF_INTC_PRIO0_SRC4_SHIFT;
}
static inline uint32_t sf_intc_prio0_src4_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_INTC_PRIO0_SRC4_SHIFT) & SF_INTC_PRIO0_SRC4_MASK;
}
/* RMW of rw field SRC4: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_intc_prio0_set_src4(uint32_t value)
{
    uint32_t v = sf_intc_prio0_read() & SF_INTC_PRIO0_RW_MASK;
    v = (v & ~SF_INTC_PRIO0_SRC4_MASK) | sf_intc_prio0_src4_encode(value);
    sf_intc_prio0_write(v);
}
static inline uint32_t sf_intc_prio0_get_src5(uint32_t reg)
{
    return (reg & SF_INTC_PRIO0_SRC5_MASK) >> SF_INTC_PRIO0_SRC5_SHIFT;
}
static inline uint32_t sf_intc_prio0_src5_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_INTC_PRIO0_SRC5_SHIFT) & SF_INTC_PRIO0_SRC5_MASK;
}
/* RMW of rw field SRC5: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_intc_prio0_set_src5(uint32_t value)
{
    uint32_t v = sf_intc_prio0_read() & SF_INTC_PRIO0_RW_MASK;
    v = (v & ~SF_INTC_PRIO0_SRC5_MASK) | sf_intc_prio0_src5_encode(value);
    sf_intc_prio0_write(v);
}
static inline uint32_t sf_intc_prio0_get_src6(uint32_t reg)
{
    return (reg & SF_INTC_PRIO0_SRC6_MASK) >> SF_INTC_PRIO0_SRC6_SHIFT;
}
static inline uint32_t sf_intc_prio0_src6_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_INTC_PRIO0_SRC6_SHIFT) & SF_INTC_PRIO0_SRC6_MASK;
}
/* RMW of rw field SRC6: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_intc_prio0_set_src6(uint32_t value)
{
    uint32_t v = sf_intc_prio0_read() & SF_INTC_PRIO0_RW_MASK;
    v = (v & ~SF_INTC_PRIO0_SRC6_MASK) | sf_intc_prio0_src6_encode(value);
    sf_intc_prio0_write(v);
}
static inline uint32_t sf_intc_prio0_get_src7(uint32_t reg)
{
    return (reg & SF_INTC_PRIO0_SRC7_MASK) >> SF_INTC_PRIO0_SRC7_SHIFT;
}
static inline uint32_t sf_intc_prio0_src7_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_INTC_PRIO0_SRC7_SHIFT) & SF_INTC_PRIO0_SRC7_MASK;
}
/* RMW of rw field SRC7: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_intc_prio0_set_src7(uint32_t value)
{
    uint32_t v = sf_intc_prio0_read() & SF_INTC_PRIO0_RW_MASK;
    v = (v & ~SF_INTC_PRIO0_SRC7_MASK) | sf_intc_prio0_src7_encode(value);
    sf_intc_prio0_write(v);
}

/* intc.PRIO1: 32-bit @ offset 0x24 - Priority of sources 8..15, 3 bits each in a 4-bit nibble (0 = never) */
#define SF_INTC_PRIO1_OFFSET UINT64_C(0x24)
#define SF_INTC_PRIO1_ADDR UINT64_C(0x180001024)
#define SF_INTC_PRIO1_WIDTH 32u
#define SF_INTC_PRIO1_RESET UINT32_C(0x11111111)
#define SF_INTC_PRIO1_RW_MASK UINT32_C(0x77777777)
SF_REGS_STATIC_ASSERT((SF_INTC_PRIO1_ADDR % 4u) == 0u, "intc.PRIO1 is not naturally aligned");
#define SF_INTC_PRIO1_SRC8_SHIFT 0u
#define SF_INTC_PRIO1_SRC8_WIDTH 3u
#define SF_INTC_PRIO1_SRC8_MASK UINT32_C(0x7)
#define SF_INTC_PRIO1_SRC8_RESET UINT32_C(0x1)
#define SF_INTC_PRIO1_SRC9_SHIFT 4u
#define SF_INTC_PRIO1_SRC9_WIDTH 3u
#define SF_INTC_PRIO1_SRC9_MASK UINT32_C(0x70)
#define SF_INTC_PRIO1_SRC9_RESET UINT32_C(0x1)
#define SF_INTC_PRIO1_SRC10_SHIFT 8u
#define SF_INTC_PRIO1_SRC10_WIDTH 3u
#define SF_INTC_PRIO1_SRC10_MASK UINT32_C(0x700)
#define SF_INTC_PRIO1_SRC10_RESET UINT32_C(0x1)
#define SF_INTC_PRIO1_SRC11_SHIFT 12u
#define SF_INTC_PRIO1_SRC11_WIDTH 3u
#define SF_INTC_PRIO1_SRC11_MASK UINT32_C(0x7000)
#define SF_INTC_PRIO1_SRC11_RESET UINT32_C(0x1)
#define SF_INTC_PRIO1_SRC12_SHIFT 16u
#define SF_INTC_PRIO1_SRC12_WIDTH 3u
#define SF_INTC_PRIO1_SRC12_MASK UINT32_C(0x70000)
#define SF_INTC_PRIO1_SRC12_RESET UINT32_C(0x1)
#define SF_INTC_PRIO1_SRC13_SHIFT 20u
#define SF_INTC_PRIO1_SRC13_WIDTH 3u
#define SF_INTC_PRIO1_SRC13_MASK UINT32_C(0x700000)
#define SF_INTC_PRIO1_SRC13_RESET UINT32_C(0x1)
#define SF_INTC_PRIO1_SRC14_SHIFT 24u
#define SF_INTC_PRIO1_SRC14_WIDTH 3u
#define SF_INTC_PRIO1_SRC14_MASK UINT32_C(0x7000000)
#define SF_INTC_PRIO1_SRC14_RESET UINT32_C(0x1)
#define SF_INTC_PRIO1_SRC15_SHIFT 28u
#define SF_INTC_PRIO1_SRC15_WIDTH 3u
#define SF_INTC_PRIO1_SRC15_MASK UINT32_C(0x70000000)
#define SF_INTC_PRIO1_SRC15_RESET UINT32_C(0x1)
static inline uint32_t sf_intc_prio1_read(void)
{
    return sf_regs_rd32_(SF_INTC_PRIO1_ADDR);
}
static inline void sf_intc_prio1_write(uint32_t value)
{
    sf_regs_wr32_(SF_INTC_PRIO1_ADDR, value);
}
static inline uint32_t sf_intc_prio1_get_src8(uint32_t reg)
{
    return (reg & SF_INTC_PRIO1_SRC8_MASK) >> SF_INTC_PRIO1_SRC8_SHIFT;
}
static inline uint32_t sf_intc_prio1_src8_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_INTC_PRIO1_SRC8_SHIFT) & SF_INTC_PRIO1_SRC8_MASK;
}
/* RMW of rw field SRC8: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_intc_prio1_set_src8(uint32_t value)
{
    uint32_t v = sf_intc_prio1_read() & SF_INTC_PRIO1_RW_MASK;
    v = (v & ~SF_INTC_PRIO1_SRC8_MASK) | sf_intc_prio1_src8_encode(value);
    sf_intc_prio1_write(v);
}
static inline uint32_t sf_intc_prio1_get_src9(uint32_t reg)
{
    return (reg & SF_INTC_PRIO1_SRC9_MASK) >> SF_INTC_PRIO1_SRC9_SHIFT;
}
static inline uint32_t sf_intc_prio1_src9_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_INTC_PRIO1_SRC9_SHIFT) & SF_INTC_PRIO1_SRC9_MASK;
}
/* RMW of rw field SRC9: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_intc_prio1_set_src9(uint32_t value)
{
    uint32_t v = sf_intc_prio1_read() & SF_INTC_PRIO1_RW_MASK;
    v = (v & ~SF_INTC_PRIO1_SRC9_MASK) | sf_intc_prio1_src9_encode(value);
    sf_intc_prio1_write(v);
}
static inline uint32_t sf_intc_prio1_get_src10(uint32_t reg)
{
    return (reg & SF_INTC_PRIO1_SRC10_MASK) >> SF_INTC_PRIO1_SRC10_SHIFT;
}
static inline uint32_t sf_intc_prio1_src10_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_INTC_PRIO1_SRC10_SHIFT) & SF_INTC_PRIO1_SRC10_MASK;
}
/* RMW of rw field SRC10: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_intc_prio1_set_src10(uint32_t value)
{
    uint32_t v = sf_intc_prio1_read() & SF_INTC_PRIO1_RW_MASK;
    v = (v & ~SF_INTC_PRIO1_SRC10_MASK) | sf_intc_prio1_src10_encode(value);
    sf_intc_prio1_write(v);
}
static inline uint32_t sf_intc_prio1_get_src11(uint32_t reg)
{
    return (reg & SF_INTC_PRIO1_SRC11_MASK) >> SF_INTC_PRIO1_SRC11_SHIFT;
}
static inline uint32_t sf_intc_prio1_src11_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_INTC_PRIO1_SRC11_SHIFT) & SF_INTC_PRIO1_SRC11_MASK;
}
/* RMW of rw field SRC11: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_intc_prio1_set_src11(uint32_t value)
{
    uint32_t v = sf_intc_prio1_read() & SF_INTC_PRIO1_RW_MASK;
    v = (v & ~SF_INTC_PRIO1_SRC11_MASK) | sf_intc_prio1_src11_encode(value);
    sf_intc_prio1_write(v);
}
static inline uint32_t sf_intc_prio1_get_src12(uint32_t reg)
{
    return (reg & SF_INTC_PRIO1_SRC12_MASK) >> SF_INTC_PRIO1_SRC12_SHIFT;
}
static inline uint32_t sf_intc_prio1_src12_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_INTC_PRIO1_SRC12_SHIFT) & SF_INTC_PRIO1_SRC12_MASK;
}
/* RMW of rw field SRC12: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_intc_prio1_set_src12(uint32_t value)
{
    uint32_t v = sf_intc_prio1_read() & SF_INTC_PRIO1_RW_MASK;
    v = (v & ~SF_INTC_PRIO1_SRC12_MASK) | sf_intc_prio1_src12_encode(value);
    sf_intc_prio1_write(v);
}
static inline uint32_t sf_intc_prio1_get_src13(uint32_t reg)
{
    return (reg & SF_INTC_PRIO1_SRC13_MASK) >> SF_INTC_PRIO1_SRC13_SHIFT;
}
static inline uint32_t sf_intc_prio1_src13_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_INTC_PRIO1_SRC13_SHIFT) & SF_INTC_PRIO1_SRC13_MASK;
}
/* RMW of rw field SRC13: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_intc_prio1_set_src13(uint32_t value)
{
    uint32_t v = sf_intc_prio1_read() & SF_INTC_PRIO1_RW_MASK;
    v = (v & ~SF_INTC_PRIO1_SRC13_MASK) | sf_intc_prio1_src13_encode(value);
    sf_intc_prio1_write(v);
}
static inline uint32_t sf_intc_prio1_get_src14(uint32_t reg)
{
    return (reg & SF_INTC_PRIO1_SRC14_MASK) >> SF_INTC_PRIO1_SRC14_SHIFT;
}
static inline uint32_t sf_intc_prio1_src14_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_INTC_PRIO1_SRC14_SHIFT) & SF_INTC_PRIO1_SRC14_MASK;
}
/* RMW of rw field SRC14: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_intc_prio1_set_src14(uint32_t value)
{
    uint32_t v = sf_intc_prio1_read() & SF_INTC_PRIO1_RW_MASK;
    v = (v & ~SF_INTC_PRIO1_SRC14_MASK) | sf_intc_prio1_src14_encode(value);
    sf_intc_prio1_write(v);
}
static inline uint32_t sf_intc_prio1_get_src15(uint32_t reg)
{
    return (reg & SF_INTC_PRIO1_SRC15_MASK) >> SF_INTC_PRIO1_SRC15_SHIFT;
}
static inline uint32_t sf_intc_prio1_src15_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_INTC_PRIO1_SRC15_SHIFT) & SF_INTC_PRIO1_SRC15_MASK;
}
/* RMW of rw field SRC15: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_intc_prio1_set_src15(uint32_t value)
{
    uint32_t v = sf_intc_prio1_read() & SF_INTC_PRIO1_RW_MASK;
    v = (v & ~SF_INTC_PRIO1_SRC15_MASK) | sf_intc_prio1_src15_encode(value);
    sf_intc_prio1_write(v);
}

/* ---------- clkrst: Clock and reset status ---------- */
/* region sysctl; window 0x180002000 + 0x1000 ; privileged access only */

/* clkrst.ID: 32-bit @ offset 0x0 - ASCII "SFCT" */
#define SF_CLKRST_ID_OFFSET UINT64_C(0x0)
#define SF_CLKRST_ID_ADDR UINT64_C(0x180002000)
#define SF_CLKRST_ID_WIDTH 32u
#define SF_CLKRST_ID_RESET UINT32_C(0x53464354)
#define SF_CLKRST_ID_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_CLKRST_ID_ADDR % 4u) == 0u, "clkrst.ID is not naturally aligned");
#define SF_CLKRST_ID_VALUE_SHIFT 0u
#define SF_CLKRST_ID_VALUE_WIDTH 32u
#define SF_CLKRST_ID_VALUE_MASK UINT32_C(0xffffffff)
#define SF_CLKRST_ID_VALUE_RESET UINT32_C(0x53464354)
static inline uint32_t sf_clkrst_id_read(void)
{
    return sf_regs_rd32_(SF_CLKRST_ID_ADDR);
}
static inline uint32_t sf_clkrst_id_get_value(uint32_t reg)
{
    return (reg & SF_CLKRST_ID_VALUE_MASK) >> SF_CLKRST_ID_VALUE_SHIFT;
}

/* clkrst.CONFIG: 32-bit @ offset 0x4 - Build configuration of the clock/reset tree */
#define SF_CLKRST_CONFIG_OFFSET UINT64_C(0x4)
#define SF_CLKRST_CONFIG_ADDR UINT64_C(0x180002004)
#define SF_CLKRST_CONFIG_WIDTH 32u
#define SF_CLKRST_CONFIG_RESET UINT32_C(0x0)
#define SF_CLKRST_CONFIG_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_CLKRST_CONFIG_ADDR % 4u) == 0u, "clkrst.CONFIG is not naturally aligned");
#define SF_CLKRST_CONFIG_MC_EN_SHIFT 0u
#define SF_CLKRST_CONFIG_MC_EN_WIDTH 1u
#define SF_CLKRST_CONFIG_MC_EN_MASK UINT32_C(0x1)
#define SF_CLKRST_CONFIG_MC_EN_RESET UINT32_C(0x0)
#define SF_CLKRST_CONFIG_NW_SHIFT 8u
#define SF_CLKRST_CONFIG_NW_WIDTH 8u
#define SF_CLKRST_CONFIG_NW_MASK UINT32_C(0xff00)
#define SF_CLKRST_CONFIG_NW_RESET UINT32_C(0x0)
#define SF_CLKRST_CONFIG_NB_SHIFT 16u
#define SF_CLKRST_CONFIG_NB_WIDTH 8u
#define SF_CLKRST_CONFIG_NB_MASK UINT32_C(0xff0000)
#define SF_CLKRST_CONFIG_NB_RESET UINT32_C(0x0)
#define SF_CLKRST_CONFIG_VERSION_SHIFT 24u
#define SF_CLKRST_CONFIG_VERSION_WIDTH 8u
#define SF_CLKRST_CONFIG_VERSION_MASK UINT32_C(0xff000000)
#define SF_CLKRST_CONFIG_VERSION_RESET UINT32_C(0x0)
static inline uint32_t sf_clkrst_config_read(void)
{
    return sf_regs_rd32_(SF_CLKRST_CONFIG_ADDR);
}
static inline uint32_t sf_clkrst_config_get_mc_en(uint32_t reg)
{
    return (reg & SF_CLKRST_CONFIG_MC_EN_MASK) >> SF_CLKRST_CONFIG_MC_EN_SHIFT;
}
static inline uint32_t sf_clkrst_config_get_nw(uint32_t reg)
{
    return (reg & SF_CLKRST_CONFIG_NW_MASK) >> SF_CLKRST_CONFIG_NW_SHIFT;
}
static inline uint32_t sf_clkrst_config_get_nb(uint32_t reg)
{
    return (reg & SF_CLKRST_CONFIG_NB_MASK) >> SF_CLKRST_CONFIG_NB_SHIFT;
}
static inline uint32_t sf_clkrst_config_get_version(uint32_t reg)
{
    return (reg & SF_CLKRST_CONFIG_VERSION_MASK) >> SF_CLKRST_CONFIG_VERSION_SHIFT;
}

/* clkrst.STATUS: 32-bit @ offset 0x8 - Sequencer and clock status (from the coherent snapshot of the reference domain) */
#define SF_CLKRST_STATUS_OFFSET UINT64_C(0x8)
#define SF_CLKRST_STATUS_ADDR UINT64_C(0x180002008)
#define SF_CLKRST_STATUS_WIDTH 32u
#define SF_CLKRST_STATUS_RESET UINT32_C(0x0)
#define SF_CLKRST_STATUS_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_CLKRST_STATUS_ADDR % 4u) == 0u, "clkrst.STATUS is not naturally aligned");
#define SF_CLKRST_STATUS_SEQ_STATE_SHIFT 0u
#define SF_CLKRST_STATUS_SEQ_STATE_WIDTH 4u
#define SF_CLKRST_STATUS_SEQ_STATE_MASK UINT32_C(0xf)
#define SF_CLKRST_STATUS_SEQ_STATE_RESET UINT32_C(0x0)
#define SF_CLKRST_STATUS_MC_STATE_SHIFT 4u
#define SF_CLKRST_STATUS_MC_STATE_WIDTH 2u
#define SF_CLKRST_STATUS_MC_STATE_MASK UINT32_C(0x30)
#define SF_CLKRST_STATUS_MC_STATE_RESET UINT32_C(0x0)
#define SF_CLKRST_STATUS_RUN_SHIFT 6u
#define SF_CLKRST_STATUS_RUN_WIDTH 1u
#define SF_CLKRST_STATUS_RUN_MASK UINT32_C(0x40)
#define SF_CLKRST_STATUS_RUN_RESET UINT32_C(0x0)
#define SF_CLKRST_STATUS_PLL_LOCKED_SHIFT 7u
#define SF_CLKRST_STATUS_PLL_LOCKED_WIDTH 1u
#define SF_CLKRST_STATUS_PLL_LOCKED_MASK UINT32_C(0x80)
#define SF_CLKRST_STATUS_PLL_LOCKED_RESET UINT32_C(0x0)
#define SF_CLKRST_STATUS_CORE_CLK_OK_SHIFT 8u
#define SF_CLKRST_STATUS_CORE_CLK_OK_WIDTH 1u
#define SF_CLKRST_STATUS_CORE_CLK_OK_MASK UINT32_C(0x100)
#define SF_CLKRST_STATUS_CORE_CLK_OK_RESET UINT32_C(0x0)
#define SF_CLKRST_STATUS_MC_CLK_OK_SHIFT 9u
#define SF_CLKRST_STATUS_MC_CLK_OK_WIDTH 1u
#define SF_CLKRST_STATUS_MC_CLK_OK_MASK UINT32_C(0x200)
#define SF_CLKRST_STATUS_MC_CLK_OK_RESET UINT32_C(0x0)
#define SF_CLKRST_STATUS_WDOG_WARN_SHIFT 10u
#define SF_CLKRST_STATUS_WDOG_WARN_WIDTH 1u
#define SF_CLKRST_STATUS_WDOG_WARN_MASK UINT32_C(0x400)
#define SF_CLKRST_STATUS_WDOG_WARN_RESET UINT32_C(0x0)
#define SF_CLKRST_STATUS_WDOG_EN_SHIFT 11u
#define SF_CLKRST_STATUS_WDOG_EN_WIDTH 1u
#define SF_CLKRST_STATUS_WDOG_EN_MASK UINT32_C(0x800)
#define SF_CLKRST_STATUS_WDOG_EN_RESET UINT32_C(0x0)
#define SF_CLKRST_STATUS_WDOG_LOCK_SHIFT 12u
#define SF_CLKRST_STATUS_WDOG_LOCK_WIDTH 1u
#define SF_CLKRST_STATUS_WDOG_LOCK_MASK UINT32_C(0x1000)
#define SF_CLKRST_STATUS_WDOG_LOCK_RESET UINT32_C(0x0)
#define SF_CLKRST_STATUS_WDOG_RST_EN_SHIFT 13u
#define SF_CLKRST_STATUS_WDOG_RST_EN_WIDTH 1u
#define SF_CLKRST_STATUS_WDOG_RST_EN_MASK UINT32_C(0x2000)
#define SF_CLKRST_STATUS_WDOG_RST_EN_RESET UINT32_C(0x0)
#define SF_CLKRST_STATUS_QTIMEOUT_SHIFT 14u
#define SF_CLKRST_STATUS_QTIMEOUT_WIDTH 1u
#define SF_CLKRST_STATUS_QTIMEOUT_MASK UINT32_C(0x4000)
#define SF_CLKRST_STATUS_QTIMEOUT_RESET UINT32_C(0x0)
#define SF_CLKRST_STATUS_CMD_DROP_SHIFT 15u
#define SF_CLKRST_STATUS_CMD_DROP_WIDTH 1u
#define SF_CLKRST_STATUS_CMD_DROP_MASK UINT32_C(0x8000)
#define SF_CLKRST_STATUS_CMD_DROP_RESET UINT32_C(0x0)
#define SF_CLKRST_STATUS_WDOG_CFG_REJECTED_SHIFT 16u
#define SF_CLKRST_STATUS_WDOG_CFG_REJECTED_WIDTH 1u
#define SF_CLKRST_STATUS_WDOG_CFG_REJECTED_MASK UINT32_C(0x10000)
#define SF_CLKRST_STATUS_WDOG_CFG_REJECTED_RESET UINT32_C(0x0)
#define SF_CLKRST_STATUS_DOMAINS_RELEASED_SHIFT 17u
#define SF_CLKRST_STATUS_DOMAINS_RELEASED_WIDTH 3u
#define SF_CLKRST_STATUS_DOMAINS_RELEASED_MASK UINT32_C(0xe0000)
#define SF_CLKRST_STATUS_DOMAINS_RELEASED_RESET UINT32_C(0x0)
#define SF_CLKRST_STATUS_SNAP_SEEN_SHIFT 31u
#define SF_CLKRST_STATUS_SNAP_SEEN_WIDTH 1u
#define SF_CLKRST_STATUS_SNAP_SEEN_MASK UINT32_C(0x80000000)
#define SF_CLKRST_STATUS_SNAP_SEEN_RESET UINT32_C(0x0)
static inline uint32_t sf_clkrst_status_read(void)
{
    return sf_regs_rd32_(SF_CLKRST_STATUS_ADDR);
}
static inline uint32_t sf_clkrst_status_get_seq_state(uint32_t reg)
{
    return (reg & SF_CLKRST_STATUS_SEQ_STATE_MASK) >> SF_CLKRST_STATUS_SEQ_STATE_SHIFT;
}
static inline uint32_t sf_clkrst_status_get_mc_state(uint32_t reg)
{
    return (reg & SF_CLKRST_STATUS_MC_STATE_MASK) >> SF_CLKRST_STATUS_MC_STATE_SHIFT;
}
static inline uint32_t sf_clkrst_status_get_run(uint32_t reg)
{
    return (reg & SF_CLKRST_STATUS_RUN_MASK) >> SF_CLKRST_STATUS_RUN_SHIFT;
}
static inline uint32_t sf_clkrst_status_get_pll_locked(uint32_t reg)
{
    return (reg & SF_CLKRST_STATUS_PLL_LOCKED_MASK) >> SF_CLKRST_STATUS_PLL_LOCKED_SHIFT;
}
static inline uint32_t sf_clkrst_status_get_core_clk_ok(uint32_t reg)
{
    return (reg & SF_CLKRST_STATUS_CORE_CLK_OK_MASK) >> SF_CLKRST_STATUS_CORE_CLK_OK_SHIFT;
}
static inline uint32_t sf_clkrst_status_get_mc_clk_ok(uint32_t reg)
{
    return (reg & SF_CLKRST_STATUS_MC_CLK_OK_MASK) >> SF_CLKRST_STATUS_MC_CLK_OK_SHIFT;
}
static inline uint32_t sf_clkrst_status_get_wdog_warn(uint32_t reg)
{
    return (reg & SF_CLKRST_STATUS_WDOG_WARN_MASK) >> SF_CLKRST_STATUS_WDOG_WARN_SHIFT;
}
static inline uint32_t sf_clkrst_status_get_wdog_en(uint32_t reg)
{
    return (reg & SF_CLKRST_STATUS_WDOG_EN_MASK) >> SF_CLKRST_STATUS_WDOG_EN_SHIFT;
}
static inline uint32_t sf_clkrst_status_get_wdog_lock(uint32_t reg)
{
    return (reg & SF_CLKRST_STATUS_WDOG_LOCK_MASK) >> SF_CLKRST_STATUS_WDOG_LOCK_SHIFT;
}
static inline uint32_t sf_clkrst_status_get_wdog_rst_en(uint32_t reg)
{
    return (reg & SF_CLKRST_STATUS_WDOG_RST_EN_MASK) >> SF_CLKRST_STATUS_WDOG_RST_EN_SHIFT;
}
static inline uint32_t sf_clkrst_status_get_qtimeout(uint32_t reg)
{
    return (reg & SF_CLKRST_STATUS_QTIMEOUT_MASK) >> SF_CLKRST_STATUS_QTIMEOUT_SHIFT;
}
static inline uint32_t sf_clkrst_status_get_cmd_drop(uint32_t reg)
{
    return (reg & SF_CLKRST_STATUS_CMD_DROP_MASK) >> SF_CLKRST_STATUS_CMD_DROP_SHIFT;
}
static inline uint32_t sf_clkrst_status_get_wdog_cfg_rejected(uint32_t reg)
{
    return (reg & SF_CLKRST_STATUS_WDOG_CFG_REJECTED_MASK) >> SF_CLKRST_STATUS_WDOG_CFG_REJECTED_SHIFT;
}
static inline uint32_t sf_clkrst_status_get_domains_released(uint32_t reg)
{
    return (reg & SF_CLKRST_STATUS_DOMAINS_RELEASED_MASK) >> SF_CLKRST_STATUS_DOMAINS_RELEASED_SHIFT;
}
static inline uint32_t sf_clkrst_status_get_snap_seen(uint32_t reg)
{
    return (reg & SF_CLKRST_STATUS_SNAP_SEEN_MASK) >> SF_CLKRST_STATUS_SNAP_SEEN_SHIFT;
}

/* clkrst.CAUSE: 32-bit @ offset 0xc - Sticky reset causes (read-only here; clearing goes through a CDC command channel that this register generator does not model). 0 POR, 1 external pin, 2 core clock absent, 3 PLL lock lost, 4 system watchdog, 5 block watchdog, 6 software SYSTEM, 7 software CONTROL, 8 software COMPUTE, 9 software MEMCTL, 10 memory-controller clock absent. */
#define SF_CLKRST_CAUSE_OFFSET UINT64_C(0xc)
#define SF_CLKRST_CAUSE_ADDR UINT64_C(0x18000200c)
#define SF_CLKRST_CAUSE_WIDTH 32u
#define SF_CLKRST_CAUSE_RESET UINT32_C(0x0)
#define SF_CLKRST_CAUSE_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_CLKRST_CAUSE_ADDR % 4u) == 0u, "clkrst.CAUSE is not naturally aligned");
#define SF_CLKRST_CAUSE_CAUSES_SHIFT 0u
#define SF_CLKRST_CAUSE_CAUSES_WIDTH 11u
#define SF_CLKRST_CAUSE_CAUSES_MASK UINT32_C(0x7ff)
#define SF_CLKRST_CAUSE_CAUSES_RESET UINT32_C(0x0)
static inline uint32_t sf_clkrst_cause_read(void)
{
    return sf_regs_rd32_(SF_CLKRST_CAUSE_ADDR);
}
static inline uint32_t sf_clkrst_cause_get_causes(uint32_t reg)
{
    return (reg & SF_CLKRST_CAUSE_CAUSES_MASK) >> SF_CLKRST_CAUSE_CAUSES_SHIFT;
}

/* clkrst.RST_INFO: 32-bit @ offset 0x10 - Reset count, last cause and released branches */
#define SF_CLKRST_RST_INFO_OFFSET UINT64_C(0x10)
#define SF_CLKRST_RST_INFO_ADDR UINT64_C(0x180002010)
#define SF_CLKRST_RST_INFO_WIDTH 32u
#define SF_CLKRST_RST_INFO_RESET UINT32_C(0x0)
#define SF_CLKRST_RST_INFO_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_CLKRST_RST_INFO_ADDR % 4u) == 0u, "clkrst.RST_INFO is not naturally aligned");
#define SF_CLKRST_RST_INFO_RESET_COUNT_SHIFT 0u
#define SF_CLKRST_RST_INFO_RESET_COUNT_WIDTH 16u
#define SF_CLKRST_RST_INFO_RESET_COUNT_MASK UINT32_C(0xffff)
#define SF_CLKRST_RST_INFO_RESET_COUNT_RESET UINT32_C(0x0)
#define SF_CLKRST_RST_INFO_LAST_CAUSE_SHIFT 16u
#define SF_CLKRST_RST_INFO_LAST_CAUSE_WIDTH 4u
#define SF_CLKRST_RST_INFO_LAST_CAUSE_MASK UINT32_C(0xf0000)
#define SF_CLKRST_RST_INFO_LAST_CAUSE_RESET UINT32_C(0x0)
#define SF_CLKRST_RST_INFO_BRANCH_RELEASED_SHIFT 24u
#define SF_CLKRST_RST_INFO_BRANCH_RELEASED_WIDTH 8u
#define SF_CLKRST_RST_INFO_BRANCH_RELEASED_MASK UINT32_C(0xff000000)
#define SF_CLKRST_RST_INFO_BRANCH_RELEASED_RESET UINT32_C(0x0)
static inline uint32_t sf_clkrst_rst_info_read(void)
{
    return sf_regs_rd32_(SF_CLKRST_RST_INFO_ADDR);
}
static inline uint32_t sf_clkrst_rst_info_get_reset_count(uint32_t reg)
{
    return (reg & SF_CLKRST_RST_INFO_RESET_COUNT_MASK) >> SF_CLKRST_RST_INFO_RESET_COUNT_SHIFT;
}
static inline uint32_t sf_clkrst_rst_info_get_last_cause(uint32_t reg)
{
    return (reg & SF_CLKRST_RST_INFO_LAST_CAUSE_MASK) >> SF_CLKRST_RST_INFO_LAST_CAUSE_SHIFT;
}
static inline uint32_t sf_clkrst_rst_info_get_branch_released(uint32_t reg)
{
    return (reg & SF_CLKRST_RST_INFO_BRANCH_RELEASED_MASK) >> SF_CLKRST_RST_INFO_BRANCH_RELEASED_SHIFT;
}

/* clkrst.CLK_EN: 32-bit @ offset 0x18 - Software clock enable per gated branch (the hardware interlock overrides a 0 while a branch is busy) */
#define SF_CLKRST_CLK_EN_OFFSET UINT64_C(0x18)
#define SF_CLKRST_CLK_EN_ADDR UINT64_C(0x180002018)
#define SF_CLKRST_CLK_EN_WIDTH 32u
#define SF_CLKRST_CLK_EN_RESET UINT32_C(0xff)
#define SF_CLKRST_CLK_EN_RW_MASK UINT32_C(0xff)
SF_REGS_STATIC_ASSERT((SF_CLKRST_CLK_EN_ADDR % 4u) == 0u, "clkrst.CLK_EN is not naturally aligned");
#define SF_CLKRST_CLK_EN_BRANCH_EN_SHIFT 0u
#define SF_CLKRST_CLK_EN_BRANCH_EN_WIDTH 8u
#define SF_CLKRST_CLK_EN_BRANCH_EN_MASK UINT32_C(0xff)
#define SF_CLKRST_CLK_EN_BRANCH_EN_RESET UINT32_C(0xff)
static inline uint32_t sf_clkrst_clk_en_read(void)
{
    return sf_regs_rd32_(SF_CLKRST_CLK_EN_ADDR);
}
static inline void sf_clkrst_clk_en_write(uint32_t value)
{
    sf_regs_wr32_(SF_CLKRST_CLK_EN_ADDR, value);
}
static inline uint32_t sf_clkrst_clk_en_get_branch_en(uint32_t reg)
{
    return (reg & SF_CLKRST_CLK_EN_BRANCH_EN_MASK) >> SF_CLKRST_CLK_EN_BRANCH_EN_SHIFT;
}
static inline uint32_t sf_clkrst_clk_en_branch_en_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_CLKRST_CLK_EN_BRANCH_EN_SHIFT) & SF_CLKRST_CLK_EN_BRANCH_EN_MASK;
}
/* RMW of rw field BRANCH_EN: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_clkrst_clk_en_set_branch_en(uint32_t value)
{
    uint32_t v = sf_clkrst_clk_en_read() & SF_CLKRST_CLK_EN_RW_MASK;
    v = (v & ~SF_CLKRST_CLK_EN_BRANCH_EN_MASK) | sf_clkrst_clk_en_branch_en_encode(value);
    sf_clkrst_clk_en_write(v);
}

/* clkrst.CLK_STAT: 32-bit @ offset 0x1c - Actual branch gate state and branch clock requests */
#define SF_CLKRST_CLK_STAT_OFFSET UINT64_C(0x1c)
#define SF_CLKRST_CLK_STAT_ADDR UINT64_C(0x18000201c)
#define SF_CLKRST_CLK_STAT_WIDTH 32u
#define SF_CLKRST_CLK_STAT_RESET UINT32_C(0x0)
#define SF_CLKRST_CLK_STAT_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_CLKRST_CLK_STAT_ADDR % 4u) == 0u, "clkrst.CLK_STAT is not naturally aligned");
#define SF_CLKRST_CLK_STAT_GATE_EN_SHIFT 0u
#define SF_CLKRST_CLK_STAT_GATE_EN_WIDTH 8u
#define SF_CLKRST_CLK_STAT_GATE_EN_MASK UINT32_C(0xff)
#define SF_CLKRST_CLK_STAT_GATE_EN_RESET UINT32_C(0x0)
#define SF_CLKRST_CLK_STAT_CLK_REQUEST_SHIFT 8u
#define SF_CLKRST_CLK_STAT_CLK_REQUEST_WIDTH 8u
#define SF_CLKRST_CLK_STAT_CLK_REQUEST_MASK UINT32_C(0xff00)
#define SF_CLKRST_CLK_STAT_CLK_REQUEST_RESET UINT32_C(0x0)
static inline uint32_t sf_clkrst_clk_stat_read(void)
{
    return sf_regs_rd32_(SF_CLKRST_CLK_STAT_ADDR);
}
static inline uint32_t sf_clkrst_clk_stat_get_gate_en(uint32_t reg)
{
    return (reg & SF_CLKRST_CLK_STAT_GATE_EN_MASK) >> SF_CLKRST_CLK_STAT_GATE_EN_SHIFT;
}
static inline uint32_t sf_clkrst_clk_stat_get_clk_request(uint32_t reg)
{
    return (reg & SF_CLKRST_CLK_STAT_CLK_REQUEST_MASK) >> SF_CLKRST_CLK_STAT_CLK_REQUEST_SHIFT;
}

/* clkrst.WDOG_CNT: 32-bit @ offset 0x2c - Current watchdog count (snapshot) */
#define SF_CLKRST_WDOG_CNT_OFFSET UINT64_C(0x2c)
#define SF_CLKRST_WDOG_CNT_ADDR UINT64_C(0x18000202c)
#define SF_CLKRST_WDOG_CNT_WIDTH 32u
#define SF_CLKRST_WDOG_CNT_RESET UINT32_C(0x0)
#define SF_CLKRST_WDOG_CNT_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_CLKRST_WDOG_CNT_ADDR % 4u) == 0u, "clkrst.WDOG_CNT is not naturally aligned");
#define SF_CLKRST_WDOG_CNT_VALUE_SHIFT 0u
#define SF_CLKRST_WDOG_CNT_VALUE_WIDTH 32u
#define SF_CLKRST_WDOG_CNT_VALUE_MASK UINT32_C(0xffffffff)
#define SF_CLKRST_WDOG_CNT_VALUE_RESET UINT32_C(0x0)
static inline uint32_t sf_clkrst_wdog_cnt_read(void)
{
    return sf_regs_rd32_(SF_CLKRST_WDOG_CNT_ADDR);
}
static inline uint32_t sf_clkrst_wdog_cnt_get_value(uint32_t reg)
{
    return (reg & SF_CLKRST_WDOG_CNT_VALUE_MASK) >> SF_CLKRST_WDOG_CNT_VALUE_SHIFT;
}

/* clkrst.CLK_MEAS: 32-bit @ offset 0x30 - Clock-monitor edge counts per window (snapshot) */
#define SF_CLKRST_CLK_MEAS_OFFSET UINT64_C(0x30)
#define SF_CLKRST_CLK_MEAS_ADDR UINT64_C(0x180002030)
#define SF_CLKRST_CLK_MEAS_WIDTH 32u
#define SF_CLKRST_CLK_MEAS_RESET UINT32_C(0x0)
#define SF_CLKRST_CLK_MEAS_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_CLKRST_CLK_MEAS_ADDR % 4u) == 0u, "clkrst.CLK_MEAS is not naturally aligned");
#define SF_CLKRST_CLK_MEAS_CORE_EDGES_SHIFT 0u
#define SF_CLKRST_CLK_MEAS_CORE_EDGES_WIDTH 16u
#define SF_CLKRST_CLK_MEAS_CORE_EDGES_MASK UINT32_C(0xffff)
#define SF_CLKRST_CLK_MEAS_CORE_EDGES_RESET UINT32_C(0x0)
#define SF_CLKRST_CLK_MEAS_MC_EDGES_SHIFT 16u
#define SF_CLKRST_CLK_MEAS_MC_EDGES_WIDTH 16u
#define SF_CLKRST_CLK_MEAS_MC_EDGES_MASK UINT32_C(0xffff0000)
#define SF_CLKRST_CLK_MEAS_MC_EDGES_RESET UINT32_C(0x0)
static inline uint32_t sf_clkrst_clk_meas_read(void)
{
    return sf_regs_rd32_(SF_CLKRST_CLK_MEAS_ADDR);
}
static inline uint32_t sf_clkrst_clk_meas_get_core_edges(uint32_t reg)
{
    return (reg & SF_CLKRST_CLK_MEAS_CORE_EDGES_MASK) >> SF_CLKRST_CLK_MEAS_CORE_EDGES_SHIFT;
}
static inline uint32_t sf_clkrst_clk_meas_get_mc_edges(uint32_t reg)
{
    return (reg & SF_CLKRST_CLK_MEAS_MC_EDGES_MASK) >> SF_CLKRST_CLK_MEAS_MC_EDGES_SHIFT;
}

/* clkrst.IRQ: 32-bit @ offset 0x34 - Watchdog warning interrupt level (cleared by servicing the watchdog) */
#define SF_CLKRST_IRQ_OFFSET UINT64_C(0x34)
#define SF_CLKRST_IRQ_ADDR UINT64_C(0x180002034)
#define SF_CLKRST_IRQ_WIDTH 32u
#define SF_CLKRST_IRQ_RESET UINT32_C(0x0)
#define SF_CLKRST_IRQ_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_CLKRST_IRQ_ADDR % 4u) == 0u, "clkrst.IRQ is not naturally aligned");
#define SF_CLKRST_IRQ_WDOG_WARN_SHIFT 0u
#define SF_CLKRST_IRQ_WDOG_WARN_WIDTH 1u
#define SF_CLKRST_IRQ_WDOG_WARN_MASK UINT32_C(0x1)
#define SF_CLKRST_IRQ_WDOG_WARN_RESET UINT32_C(0x0)
static inline uint32_t sf_clkrst_irq_read(void)
{
    return sf_regs_rd32_(SF_CLKRST_IRQ_ADDR);
}
static inline uint32_t sf_clkrst_irq_get_wdog_warn(uint32_t reg)
{
    return (reg & SF_CLKRST_IRQ_WDOG_WARN_MASK) >> SF_CLKRST_IRQ_WDOG_WARN_SHIFT;
}

/* ---------- sramc: SRAM controller control and status ---------- */
/* region sysctl; window 0x180003000 + 0x1000 ; privileged access only */

/* sramc.CTRL: 32-bit @ offset 0x0 - Master enables and flush */
#define SF_SRAMC_CTRL_OFFSET UINT64_C(0x0)
#define SF_SRAMC_CTRL_ADDR UINT64_C(0x180003000)
#define SF_SRAMC_CTRL_WIDTH 32u
#define SF_SRAMC_CTRL_RESET UINT32_C(0xf)
#define SF_SRAMC_CTRL_RW_MASK UINT32_C(0x10f)
SF_REGS_STATIC_ASSERT((SF_SRAMC_CTRL_ADDR % 4u) == 0u, "sramc.CTRL is not naturally aligned");
#define SF_SRAMC_CTRL_SRC_EN_SHIFT 0u
#define SF_SRAMC_CTRL_SRC_EN_WIDTH 4u
#define SF_SRAMC_CTRL_SRC_EN_MASK UINT32_C(0xf)
#define SF_SRAMC_CTRL_SRC_EN_RESET UINT32_C(0xf)
#define SF_SRAMC_CTRL_FLUSH_SHIFT 8u
#define SF_SRAMC_CTRL_FLUSH_WIDTH 1u
#define SF_SRAMC_CTRL_FLUSH_MASK UINT32_C(0x100)
#define SF_SRAMC_CTRL_FLUSH_RESET UINT32_C(0x0)
static inline uint32_t sf_sramc_ctrl_read(void)
{
    return sf_regs_rd32_(SF_SRAMC_CTRL_ADDR);
}
static inline void sf_sramc_ctrl_write(uint32_t value)
{
    sf_regs_wr32_(SF_SRAMC_CTRL_ADDR, value);
}
static inline uint32_t sf_sramc_ctrl_get_src_en(uint32_t reg)
{
    return (reg & SF_SRAMC_CTRL_SRC_EN_MASK) >> SF_SRAMC_CTRL_SRC_EN_SHIFT;
}
static inline uint32_t sf_sramc_ctrl_src_en_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_SRAMC_CTRL_SRC_EN_SHIFT) & SF_SRAMC_CTRL_SRC_EN_MASK;
}
/* RMW of rw field SRC_EN: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_sramc_ctrl_set_src_en(uint32_t value)
{
    uint32_t v = sf_sramc_ctrl_read() & SF_SRAMC_CTRL_RW_MASK;
    v = (v & ~SF_SRAMC_CTRL_SRC_EN_MASK) | sf_sramc_ctrl_src_en_encode(value);
    sf_sramc_ctrl_write(v);
}
static inline uint32_t sf_sramc_ctrl_get_flush(uint32_t reg)
{
    return (reg & SF_SRAMC_CTRL_FLUSH_MASK) >> SF_SRAMC_CTRL_FLUSH_SHIFT;
}
static inline uint32_t sf_sramc_ctrl_flush_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_SRAMC_CTRL_FLUSH_SHIFT) & SF_SRAMC_CTRL_FLUSH_MASK;
}
/* RMW of rw field FLUSH: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_sramc_ctrl_set_flush(uint32_t value)
{
    uint32_t v = sf_sramc_ctrl_read() & SF_SRAMC_CTRL_RW_MASK;
    v = (v & ~SF_SRAMC_CTRL_FLUSH_MASK) | sf_sramc_ctrl_flush_encode(value);
    sf_sramc_ctrl_write(v);
}

/* sramc.STATUS: 32-bit @ offset 0x8 - Controller status */
#define SF_SRAMC_STATUS_OFFSET UINT64_C(0x8)
#define SF_SRAMC_STATUS_ADDR UINT64_C(0x180003008)
#define SF_SRAMC_STATUS_WIDTH 32u
#define SF_SRAMC_STATUS_RESET UINT32_C(0x0)
#define SF_SRAMC_STATUS_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_SRAMC_STATUS_ADDR % 4u) == 0u, "sramc.STATUS is not naturally aligned");
#define SF_SRAMC_STATUS_IDLE_SHIFT 0u
#define SF_SRAMC_STATUS_IDLE_WIDTH 1u
#define SF_SRAMC_STATUS_IDLE_MASK UINT32_C(0x1)
#define SF_SRAMC_STATUS_IDLE_RESET UINT32_C(0x0)
#define SF_SRAMC_STATUS_RSP_OVERFLOW_SHIFT 1u
#define SF_SRAMC_STATUS_RSP_OVERFLOW_WIDTH 1u
#define SF_SRAMC_STATUS_RSP_OVERFLOW_MASK UINT32_C(0x2)
#define SF_SRAMC_STATUS_RSP_OVERFLOW_RESET UINT32_C(0x0)
#define SF_SRAMC_STATUS_BANK_PROTO_SHIFT 2u
#define SF_SRAMC_STATUS_BANK_PROTO_WIDTH 1u
#define SF_SRAMC_STATUS_BANK_PROTO_MASK UINT32_C(0x4)
#define SF_SRAMC_STATUS_BANK_PROTO_RESET UINT32_C(0x0)
static inline uint32_t sf_sramc_status_read(void)
{
    return sf_regs_rd32_(SF_SRAMC_STATUS_ADDR);
}
static inline uint32_t sf_sramc_status_get_idle(uint32_t reg)
{
    return (reg & SF_SRAMC_STATUS_IDLE_MASK) >> SF_SRAMC_STATUS_IDLE_SHIFT;
}
static inline uint32_t sf_sramc_status_get_rsp_overflow(uint32_t reg)
{
    return (reg & SF_SRAMC_STATUS_RSP_OVERFLOW_MASK) >> SF_SRAMC_STATUS_RSP_OVERFLOW_SHIFT;
}
static inline uint32_t sf_sramc_status_get_bank_proto(uint32_t reg)
{
    return (reg & SF_SRAMC_STATUS_BANK_PROTO_MASK) >> SF_SRAMC_STATUS_BANK_PROTO_SHIFT;
}

/* sramc.PERF_CTRL: 32-bit @ offset 0x10 - Performance counter selection and clear */
#define SF_SRAMC_PERF_CTRL_OFFSET UINT64_C(0x10)
#define SF_SRAMC_PERF_CTRL_ADDR UINT64_C(0x180003010)
#define SF_SRAMC_PERF_CTRL_WIDTH 32u
#define SF_SRAMC_PERF_CTRL_RESET UINT32_C(0x0)
#define SF_SRAMC_PERF_CTRL_RW_MASK UINT32_C(0x7f)
SF_REGS_STATIC_ASSERT((SF_SRAMC_PERF_CTRL_ADDR % 4u) == 0u, "sramc.PERF_CTRL is not naturally aligned");
#define SF_SRAMC_PERF_CTRL_SEL_SHIFT 0u
#define SF_SRAMC_PERF_CTRL_SEL_WIDTH 7u
#define SF_SRAMC_PERF_CTRL_SEL_MASK UINT32_C(0x7f)
#define SF_SRAMC_PERF_CTRL_SEL_RESET UINT32_C(0x0)
#define SF_SRAMC_PERF_CTRL_CLEAR_SHIFT 8u
#define SF_SRAMC_PERF_CTRL_CLEAR_WIDTH 1u
#define SF_SRAMC_PERF_CTRL_CLEAR_MASK UINT32_C(0x100)
#define SF_SRAMC_PERF_CTRL_CLEAR_RESET UINT32_C(0x0)
static inline uint32_t sf_sramc_perf_ctrl_read(void)
{
    return sf_regs_rd32_(SF_SRAMC_PERF_CTRL_ADDR);
}
static inline void sf_sramc_perf_ctrl_write(uint32_t value)
{
    sf_regs_wr32_(SF_SRAMC_PERF_CTRL_ADDR, value);
}
static inline uint32_t sf_sramc_perf_ctrl_get_sel(uint32_t reg)
{
    return (reg & SF_SRAMC_PERF_CTRL_SEL_MASK) >> SF_SRAMC_PERF_CTRL_SEL_SHIFT;
}
static inline uint32_t sf_sramc_perf_ctrl_sel_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_SRAMC_PERF_CTRL_SEL_SHIFT) & SF_SRAMC_PERF_CTRL_SEL_MASK;
}
/* RMW of rw field SEL: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */
static inline void sf_sramc_perf_ctrl_set_sel(uint32_t value)
{
    uint32_t v = sf_sramc_perf_ctrl_read() & SF_SRAMC_PERF_CTRL_RW_MASK;
    v = (v & ~SF_SRAMC_PERF_CTRL_SEL_MASK) | sf_sramc_perf_ctrl_sel_encode(value);
    sf_sramc_perf_ctrl_write(v);
}
static inline uint32_t sf_sramc_perf_ctrl_clear_encode(uint32_t value)
{
    return ((uint32_t)(value) << SF_SRAMC_PERF_CTRL_CLEAR_SHIFT) & SF_SRAMC_PERF_CTRL_CLEAR_MASK;
}
/* w1p: write 1 to the chosen bits of CLEAR (pulse); other rw fields keep their value, other write-one fields get 0. */
static inline void sf_sramc_perf_ctrl_pulse_clear(uint32_t bits)
{
    uint32_t v = sf_sramc_perf_ctrl_read() & SF_SRAMC_PERF_CTRL_RW_MASK;
    sf_sramc_perf_ctrl_write(v | sf_sramc_perf_ctrl_clear_encode(bits));
}

/* sramc.PERF_VAL: 32-bit @ offset 0x14 - Value of the counter selected by PERF_CTRL.SEL (32 bits, wraps) */
#define SF_SRAMC_PERF_VAL_OFFSET UINT64_C(0x14)
#define SF_SRAMC_PERF_VAL_ADDR UINT64_C(0x180003014)
#define SF_SRAMC_PERF_VAL_WIDTH 32u
#define SF_SRAMC_PERF_VAL_RESET UINT32_C(0x0)
#define SF_SRAMC_PERF_VAL_RW_MASK UINT32_C(0x0)
SF_REGS_STATIC_ASSERT((SF_SRAMC_PERF_VAL_ADDR % 4u) == 0u, "sramc.PERF_VAL is not naturally aligned");
#define SF_SRAMC_PERF_VAL_VALUE_SHIFT 0u
#define SF_SRAMC_PERF_VAL_VALUE_WIDTH 32u
#define SF_SRAMC_PERF_VAL_VALUE_MASK UINT32_C(0xffffffff)
#define SF_SRAMC_PERF_VAL_VALUE_RESET UINT32_C(0x0)
static inline uint32_t sf_sramc_perf_val_read(void)
{
    return sf_regs_rd32_(SF_SRAMC_PERF_VAL_ADDR);
}
static inline uint32_t sf_sramc_perf_val_get_value(uint32_t reg)
{
    return (reg & SF_SRAMC_PERF_VAL_VALUE_MASK) >> SF_SRAMC_PERF_VAL_VALUE_SHIFT;
}

/* Returns 1 if the hardware's REGMAP_HASH equals the definition this header was generated from. */
static inline int sf_regs_hardware_matches(void)
{
    return sf_sysid_regmap_hash_read() == SF_REGS_MAP_HASH;
}

#ifdef __cplusplus
}
#endif
#endif /* SF_REGS_H */
