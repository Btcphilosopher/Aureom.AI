/* sf_regs_hardware_matches(): compares the hardware REGMAP_HASH with the one this header was generated from. */
#include <stdint.h>
#include <stdio.h>
#define SF_REGS_CUSTOM_ACCESS 1
static uint64_t g_hash;
uint32_t sf_regs_rd32_(uint64_t a);
void sf_regs_wr32_(uint64_t a, uint32_t v);
uint64_t sf_regs_rd64n_(uint64_t a);
void sf_regs_wr64n_(uint64_t a, uint64_t v);
#include "sf_regs.h"
uint32_t sf_regs_rd32_(uint64_t a) { return a == SF_SYSID_REGMAP_HASH_ADDR ? (uint32_t)g_hash : (uint32_t)(g_hash >> 32); }
void sf_regs_wr32_(uint64_t a, uint32_t v) { (void)a; (void)v; }
uint64_t sf_regs_rd64n_(uint64_t a) { (void)a; return g_hash; }
void sf_regs_wr64n_(uint64_t a, uint64_t v) { (void)a; (void)v; }
int main(void)
{
    int fail = 0;
    g_hash = SF_REGS_MAP_HASH;
    if (!sf_regs_hardware_matches()) { printf("FAIL: matching hash rejected\n"); fail++; }
    g_hash ^= UINT64_C(1) << 37;
    if (sf_regs_hardware_matches()) { printf("FAIL: wrong hash accepted\n"); fail++; }
    g_hash = SF_REGS_MAP_HASH ^ 1u;
    if (sf_regs_hardware_matches()) { printf("FAIL: wrong hash (bit 0) accepted\n"); fail++; }
    printf(fail ? "SYSID TEST FAILED\n" : "SYSID TEST PASSED\n");
    return fail != 0;
}
