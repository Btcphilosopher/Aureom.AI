# SilicaFlux-V SoC timing constraints (functional mode).
# CLK_PERIOD is set by the flow (default 20 ns = 50 MHz).
set period $::env(CLK_PERIOD_NS)
create_clock -name clk -period $period [get_ports clk]
create_clock -name tck -period 100.0 [get_ports tck]
# JTAG and system clocks are asynchronous; every crossing goes through
# sfv_sync two-flop synchronisers / toggle handshakes (docs/CLOCK_RESET.md).
set_clock_groups -asynchronous -group {clk} -group {tck}
set_clock_uncertainty 0.25 [get_clocks clk]
set_clock_transition 0.15 [get_clocks clk]
# I/O budgets: 30% of the period outside the chip (pads + board)
set io_in  [expr 0.3 * $period]
set_input_delay  $io_in -clock clk [get_ports {uart_rx spi_miso gpio_i*}]
set_output_delay $io_in -clock clk [get_ports {uart_tx spi_sck spi_mosi spi_cs0_n gpio_o* gpio_oe* test_pass test_fail test_status* cpu_sleep}]
set_input_delay  20.0 -clock tck [get_ports {tms tdi}]
set_output_delay 20.0 -clock tck [get_ports {tdo tdo_oe}]
# reset pin and test-mode pin are asynchronous / static in functional mode
set_false_path -from [get_ports rst_ni]
set_false_path -from [get_ports test_mode]
set_load 0.02 [all_outputs]
set_input_transition 0.2 [all_inputs]
