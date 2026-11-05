# Register map

APB3, 32-bit. `sf_memflow_top` decodes `paddr[12]`: 0 → DMA, 1 → control block.

## DMA (`0x0000`)

| Offset | Name | Access | Fields |
|---|---|---|---|
| 0x000 | ID | RO | `0x5346_444D` ("SFDM") |
| 0x004 | CAPS | RO | `{NSI[7:0], NSO[7:0], beat_bytes[7:0], NCH[7:0]}` |
| 0x008 | IRQ_STATUS | RO | bit c = channel c interrupt pending |
| 0x100 + 0x40·c | CTRL | RW | [0] START (W1) · [1] IRQ_EN · [2] SRC_STREAM · [3] DST_STREAM · [7:4] BURST_LOG2 · [8] MODE_2D · [9] ABORT (W1) · [13:12] SRC_PORT · [17:16] DST_PORT |
| +0x04 | STATUS | RW | [0] BUSY · [1] DONE (W1C) · [2] ERR (W1C) · [7:4] ERR_CODE |
| +0x08 | SRC | RW | source byte address (beat-aligned for memory) |
| +0x0C | DST | RW | destination byte address |
| +0x10 | LEN | RW | bytes per row (any value ≥ 1; the last beat of each row carries a tail strobe) |
| +0x14 | ROWS | RW | rows for 2-D transfers (0 is treated as 1) |
| +0x18 | SRC_STRIDE | RW | 2-D source pitch (bytes, beat-aligned) |
| +0x1C | DST_STRIDE | RW | 2-D destination pitch |
| +0x20 | BEATS | RO | beats delivered (stream handshakes + successful write acks) |

Registers are locked while BUSY; only ABORT is accepted. START while BUSY is ignored.

**ERR_CODE:** 1 ZERO_LEN · 2 ALIGN · 3 OVERFLOW (whole 2-D footprint beyond 2³² checked at start)
· 4 RD_BUS · 5 WR_BUS · 6 ABORT · 7 INVALID (stream→stream). Codes 1–3 and 7 are raised before
any data moves. Codes 4–6 drain in-flight beats, then clear BUSY.

## Control block (`0x1000`)

| Offset | Name | Access | Fields |
|---|---|---|---|
| 0x000 | ID | RO | `0x5346_4358` ("SFCX") |
| 0x004 | VEC_OP | RW | 0 ADD, 1 MUL, 2 DOT, 3 AXPY |
| 0x008 | VEC_ALPHA | RW | int16 α for AXPY |
| 0x00C | TEN_K | RW | K steps per tensor tile |
| 0x010 | REUSE_REPLAY | RW | B-tile replays (0 → 1) |
| 0x014 | PERF_CLEAR | W1 | clears accelerator perf counters |
| 0x018 | CYCLE | RO | free-running cycle counter |
| 0x020–0x02C | TEN_MAC / STALL_IN / STALL_ACC / TILES | RO | tensor perf counters |
| 0x030–0x038 | VEC_ACTIVE / STARVE / OSTALL | RO | vector perf counters |
| 0x040 | SPM_INJ_CTRL | RW | [0] inj_en · [11:8] bank |
| 0x044–0x04C | SPM_INJ_MASK0..2 | RW | stored-word XOR mask (bits 95:0) |
| 0x050 / 0x054 | SPM_CNT_CORR / UNCORR | RO | ECC event counters (saturating 16 bit) |
| 0x058 / 0x05C | SPM_CONFLICT / SPM_STALL | RO | bank-conflict cycles, port-stall cycles |
| 0x060 | MBIST_CTRL | W | [0] START · [1] checkerboard background |
| 0x064 | MBIST_STATUS | RO | [0] busy · [1] done · [2] fail · [31:16] failing-bank mask |
| 0x068 | MBIST_FAIL_ADDR | RO | first failing word address |
| 0x06C | LP_CTRL | RW | [0] SPM light-sleep |
