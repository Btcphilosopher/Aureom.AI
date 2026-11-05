// =============================================================================
// SilicaFlux MemoryFlow :: shared testbench utilities (simulation only)
// Result protocol parsed by memoryflow.verify.rtl_runner:
//   MF_METRIC <key>=<value>      numeric measurement from RTL simulation
//   MF_RESULT PASS|FAIL errors=<n> checks=<n>
// =============================================================================
`ifndef SF_TB_COMMON_SVH
`define SF_TB_COMMON_SVH

int tb_errors = 0;
int tb_checks = 0;

`define CHECK(C__, M__) \
  begin \
    tb_checks++; \
    if (!(C__)) begin \
      tb_errors++; \
      if (tb_errors <= 20) $display("[%0t] CHECK FAILED: %s", $time, M__); \
    end \
  end

// NOTE: Verilator substitutes macro arguments inside string literals, so the
// argument names below are chosen to never appear in the message text.
`define CHECK_EQ(G__, E__, M__) \
  begin \
    tb_checks++; \
    if ((G__) !== (E__)) begin \
      tb_errors++; \
      if (tb_errors <= 20) $display("[%0t] CHECK FAILED: %s got=%h exp=%h", $time, M__, (G__), (E__)); \
    end \
  end

task automatic tb_metric(input string key, input real value);
  $display("MF_METRIC %s=%0.6f", key, value);
endtask

task automatic tb_finish();
  if (tb_errors == 0)
    $display("MF_RESULT PASS errors=0 checks=%0d", tb_checks);
  else
    $display("MF_RESULT FAIL errors=%0d checks=%0d", tb_errors, tb_checks);
  $finish;
endtask

`endif
