// =============================================================================
// SilicaFlux MemoryFlow :: SECDED (extended Hamming) constant functions
// Included INSIDE sf_ecc_secded_enc / sf_ecc_secded_dec.  Requires parameter K
// (data bits) in the including scope.
//
// Systematic layout of the stored codeword (K + R + 1 bits):
//     { overall_parity, check[R-1:0], data[K-1:0] }
// Data bit j occupies Hamming position dpos(j) = j-th integer >= 3 that is not
// a power of two.  check[i] covers every position with bit i set.  The overall
// parity bit makes the full codeword even parity -> double-error detection.
// The Python golden model memoryflow.verify.golden.secded_* is bit-identical.
// (Written in a conservative style -- no while/return -- for Yosys/Icarus.)
// =============================================================================

// Number of Hamming check bits R for K data bits (smallest r: 2^r >= K+r+1)
// is computed in each module header as  $clog2(K + 1 + $clog2(K + 1)),
// which is exact for all K >= 1 (one fixed-point step of r = clog2(K+1+r)).

// Hamming position of data bit j.
function automatic integer sf_ecc_dpos(input integer j);
  integer p, n;
  begin
    sf_ecc_dpos = 0;
    n           = 0;
    for (p = 3; p < 1024; p = p + 1) begin
      if ((p & (p - 1)) != 0) begin
        if (n == j) sf_ecc_dpos = p;
        n = n + 1;
      end
    end
  end
endfunction

// K-bit mask of data bits covered by check bit i.
function automatic logic [K-1:0] sf_ecc_cmask(input integer i);
  integer j, pos;
  begin
    sf_ecc_cmask = '0;
    for (j = 0; j < K; j = j + 1) begin
      pos = sf_ecc_dpos(j);
      sf_ecc_cmask[j] = ((pos >> i) & 1) == 1;
    end
  end
endfunction
