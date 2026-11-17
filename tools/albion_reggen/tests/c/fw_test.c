/* Behavioural test of the generated C API (kitchen-sink map) against a logging mock bus.
 * Build twice: -DSF_REGS_NATIVE64=0 (32-bit initiator: split 64-bit access) and =1 (native 64-bit). */
#include <setjmp.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

static jmp_buf g_fault;
#define SF_REGS_FAULT() longjmp(g_fault, 1)
#define SF_REGS_CUSTOM_ACCESS 1

uint32_t sf_regs_rd32_(uint64_t addr);
void sf_regs_wr32_(uint64_t addr, uint32_t v);
uint64_t sf_regs_rd64n_(uint64_t addr);
void sf_regs_wr64n_(uint64_t addr, uint64_t v);

#include "sf_regs.h"

typedef struct { uint64_t addr; uint64_t val; int write; int size; } acc_t;
static acc_t g_log[512];
static int g_n;
typedef struct { uint64_t addr; uint64_t val; int used; } cell_t;
static cell_t g_mem[128];
/* scripted reads: successive reads of an address return successive script values */
typedef struct { uint64_t addr; uint32_t vals[8]; int n, pos; } script_t;
static script_t g_script[4];
static int g_nscript;

static cell_t *cell(uint64_t a)
{
    for (int i = 0; i < 128; i++) { if (g_mem[i].used && g_mem[i].addr == a) { return &g_mem[i]; } }
    for (int i = 0; i < 128; i++) { if (!g_mem[i].used) { g_mem[i].used = 1; g_mem[i].addr = a; g_mem[i].val = 0; return &g_mem[i]; } }
    abort();
}
static void put(uint64_t a, uint64_t v) { cell(a)->val = v; }
static void reset_mock(void) { for (int i = 0; i < 128; i++) { g_mem[i].used = 0; } g_n = 0; g_nscript = 0; }
static void logacc(uint64_t a, uint64_t v, int w, int s) { g_log[g_n].addr = a; g_log[g_n].val = v; g_log[g_n].write = w; g_log[g_n].size = s; g_n++; }

uint32_t sf_regs_rd32_(uint64_t a)
{
    uint32_t v = (uint32_t)cell(a)->val;
    for (int i = 0; i < g_nscript; i++) { if (g_script[i].addr == a && g_script[i].pos < g_script[i].n) { v = g_script[i].vals[g_script[i].pos++]; } }
    logacc(a, v, 0, 4); return v;
}
void sf_regs_wr32_(uint64_t a, uint32_t v) { logacc(a, v, 1, 4); put(a, v); }
uint64_t sf_regs_rd64n_(uint64_t a) { uint64_t v = cell(a)->val; logacc(a, v, 0, 8); return v; }
void sf_regs_wr64n_(uint64_t a, uint64_t v) { logacc(a, v, 1, 8); put(a, v); }

static int g_fail;
#define CHECK(c) do { if (!(c)) { printf("FAIL line %d: %s\n", __LINE__, #c); g_fail++; } } while (0)

static int count(int write) { int n = 0; for (int i = 0; i < g_n; i++) { n += (g_log[i].write == write); } return n; }
static acc_t last_write(void) { for (int i = g_n - 1; i >= 0; i--) { if (g_log[i].write) { return g_log[i]; } } acc_t z = {0, 0, 0, 0}; return z; }

int main(void)
{
    /* ---- compile-time facts */
    SF_REGS_STATIC_ASSERT((SF_KS_C_BIG_ADDR % 8u) == 0u, "64-bit register aligned");
    SF_REGS_STATIC_ASSERT(SF_KS_A_WORD_COUNT == 4u, "array count");

    /* ---- RMW of an rw field must not write back a w1c flag that reads as 1 */
    reset_mock(); put(SF_KS_A_MIXED_ADDR, 0x109u);                /* EN=9, FLAG=1 (set by hardware) */
    sf_ks_a_mixed_set_en(5u);
    CHECK(last_write().val == 0x005u);                            /* FLAG written as 0: not cleared */
    CHECK(last_write().addr == SF_KS_A_MIXED_ADDR);

    /* ---- clearing the w1c flag preserves rw bits and writes 1 only to the flag */
    reset_mock(); put(SF_KS_A_MIXED_ADDR, 0x109u);
    sf_ks_a_mixed_clear_flag(1u);
    CHECK(last_write().val == 0x109u);                            /* EN=9 kept, FLAG bit written as 1 */

    /* ---- registers with only write-one fields need no read-back at all */
    reset_mock();
    sf_ks_a_flags_clear_c_hw(0x3u);
    CHECK(last_write().val == 0x00003u);
    sf_ks_a_flags_raise_s_hw(0x1u);
    CHECK(last_write().val == 0x01000u);                          /* bit 12 only */
    CHECK(count(0) == 0);                                         /* no reads were issued */

    /* ---- rw + pulse in one register: pulsing KICK keeps DATA, setting DATA does not pulse */
    reset_mock(); put(SF_KS_A_GATED_ADDR, 0x1BEEFu);              /* DATA=BEEF, KICK reads 0 in hardware; model a stuck 1 */
    sf_ks_a_gated_pulse_kick(1u);
    CHECK(last_write().val == 0x1BEEFu);
    reset_mock(); put(SF_KS_A_GATED_ADDR, 0x1BEEFu);
    sf_ks_a_gated_set_data(0x1234u);
    CHECK(last_write().val == 0x01234u);                          /* KICK bit written as 0 */

    /* ---- field encode/decode helpers */
    CHECK(sf_ks_a_rwmix_f_top_encode(0xABu) == 0xAB000000u);
    CHECK(sf_ks_a_rwmix_f_plain_encode(0x1FFu) == 0x00FF0000u);   /* value masked to the field */
    CHECK(sf_ks_a_rwmix_get_f_sw(0x00001200u) == 0x12u);
    reset_mock();
    CHECK(SF_KS_A_RWMIX_RESET == 0x00A52211u);

    /* ---- reading with a side effect: exactly one read, no write */
    reset_mock();
    (void)sf_ks_a_popread_read();
    CHECK(g_n == 1 && g_log[0].write == 0);

    /* ---- 64-bit registers */
    reset_mock();
    sf_ks_c_big_write(UINT64_C(0x1122334455667788));
#if SF_REGS_NATIVE64
    CHECK(count(1) == 1 && g_log[0].size == 8 && g_log[0].val == UINT64_C(0x1122334455667788));
#else
    CHECK(count(1) == 2);
    CHECK(g_log[0].addr == SF_KS_C_BIG_ADDR && g_log[0].val == 0x55667788u);          /* low word first */
    CHECK(g_log[1].addr == SF_KS_C_BIG_ADDR + 4u && g_log[1].val == 0x11223344u);
#endif
    CHECK(sf_ks_c_big_read() == UINT64_C(0x1122334455667788));

    /* ---- a free-running 64-bit counter read as two halves cannot tear (high-low-high) */
    reset_mock();
    put(sf_ks_c_cnt_addr(1) + 4u, 0); put(sf_ks_c_cnt_addr(1), 0);
#if !SF_REGS_NATIVE64
    g_script[0].addr = sf_ks_c_cnt_addr(1) + 4u; g_script[0].n = 4; g_script[0].vals[0] = 0; g_script[0].vals[1] = 1; g_script[0].vals[2] = 1; g_script[0].vals[3] = 1;
    g_script[1].addr = sf_ks_c_cnt_addr(1);       g_script[1].n = 2; g_script[1].vals[0] = 0xFFFFFFFEu; g_script[1].vals[1] = 0x00000003u;
    g_nscript = 2;                                                    /* the counter rolls over between the reads */
    CHECK(sf_ks_c_cnt_read(1u) == UINT64_C(0x0000000100000003));
    CHECK(g_n == 6);                                                   /* hi, lo, hi (retry) hi, lo, hi */
#else
    put(sf_ks_c_cnt_addr(1), UINT64_C(0x100000003));
    CHECK(sf_ks_c_cnt_read(1u) == UINT64_C(0x100000003));
    CHECK(g_n == 1 && g_log[0].size == 8);
#endif

    /* ---- array index check */
    reset_mock();
    if (setjmp(g_fault) == 0) { (void)sf_ks_a_word_read(3u); } else { CHECK(0); }
    int faulted = 0;
    if (setjmp(g_fault) == 0) { (void)sf_ks_a_word_read(4u); } else { faulted = 1; }
    CHECK(faulted == 1);
    faulted = 0;
    if (setjmp(g_fault) == 0) { sf_ks_c_cnt_addr(4u); } else { faulted = 1; }
    CHECK(faulted == 1);
    CHECK(sf_ks_a_word_addr(3u) == SF_KS_A_WORD_ADDR + 3u * 4u);
    CHECK(sf_ks_a_arr_addr(2u) == SF_KS_A_ARR_ADDR + 2u * 8u);       /* stride larger than the register */

    /* ---- every access made above was one naturally aligned access of the register's width */
    reset_mock();
    sf_ks_a_mixed_set_en(1u); sf_ks_c_big_write(1u); (void)sf_ks_c_big_read(); (void)sf_ks_c_cnt_read(2u);
    sf_ks_a_word_write(2u, 7u); (void)sf_ks_a_arr_read(1u);
    for (int i = 0; i < g_n; i++) { CHECK(g_log[i].addr % (uint64_t)g_log[i].size == 0u); CHECK(g_log[i].size == 4 || g_log[i].size == 8); }

    printf(g_fail ? "C TEST FAILED (%d)\n" : "C TEST PASSED\n", g_fail);
    return g_fail != 0;
}
