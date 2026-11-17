"""Mutation testing of the verification flow.

Realistic bugs are injected into the generated RTL of the kitchen-sink map; the
model-driven testbench (with the ALP link checker) must fail for every one.  A
mutant that survives would mean some behaviour is not actually checked.
"""

import os
import re
import unittest
from concurrent.futures import ThreadPoolExecutor

from helpers import KS_DEF, TmpCase, model, need
from albion_reggen import simflow


def sub(text, pattern, repl, count=1, flags=0):
    new, n = re.subn(pattern, repl, text, count=count, flags=flags)
    if n == 0:
        raise AssertionError(f"mutation pattern not found: {pattern}")
    return new


def on(fname, fn):
    def m(files):
        files[fname] = fn(files[fname])
        return files
    return m


def drop_last_or_term(text, lhs):
    """Remove the last top-level '|' term of 'assign <lhs> = a | b | c;'."""
    i = text.index(f"assign {lhs} = ")
    j = text.index(";", i)
    expr = text[i + len(f"assign {lhs} = "):j]
    depth, cut = 0, None
    for k, ch in enumerate(expr):
        depth += (ch == "(") - (ch == ")")
        if ch == "|" and depth == 0 and (expr[k - 1] == " "):
            cut = k
    if cut is None:
        raise AssertionError("no top-level OR term to drop")
    return text[:i] + f"assign {lhs} = " + expr[:cut].rstrip() + text[j:]


def mutants(m):
    ix = {i.name: i.index for i in m.instances}
    R = lambda n: f"r{ix[n]}"
    M = {
        # ---- interface / ALP handshake
        "if_ready_always_high":       on("sf_reg_interface.sv", lambda t: sub(t, r"assign req_ready_o = [^;]+;", "assign req_ready_o = 1'b1;")),
        "if_ready_ignores_rsp_ready": on("sf_reg_interface.sv", lambda t: sub(t, r"assign req_ready_o = [^;]+;", "assign req_ready_o = !rsp_valid_q;")),
        "if_data_on_error":           on("sf_reg_interface.sv", lambda t: sub(t, r"if \(\(acc_status_i == sf_albion_pkg::SF_ST_OKAY\) && \(req_i.op == sf_albion_pkg::SF_OP_READ\)\)", "if (req_i.op == sf_albion_pkg::SF_OP_READ)")),
        "if_is_write_wrong":          on("sf_reg_interface.sv", lambda t: sub(t, r"rsp_d.meta.is_write = [^;]+;", "rsp_d.meta.is_write = 1'b0;")),
        "if_tag_not_echoed":          on("sf_reg_interface.sv", lambda t: sub(t, r"rsp_d.tag\s+= req_i.tag;", "rsp_d.tag = 8'h00;")),
        "if_response_dropped_early":  on("sf_reg_interface.sv", lambda t: sub(t, r"end else if \(rsp_ready_i\) begin\n\s+rsp_valid_q <= 1'b0;", "end else if (1'b1) begin\n      rsp_valid_q <= 1'b0;")),
        "if_legality_skipped":        on("sf_reg_interface.sv", lambda t: sub(t, r"assign acc_legal_o = [^;]+;", "assign acc_legal_o = sf_albion_pkg::SF_ST_OKAY;")),
        # ---- decoder
        "dec_hole_ignored":           on("sf_reg_decoder.sv", lambda t: sub(t, r"assign hole = [^;]+;", "assign hole = 1'b0;")),
        "dec_permissions_ignored":    on("sf_reg_decoder.sv", lambda t: sub(t, r"assign deny = [^;]+;", "assign deny = 1'b0;")),
        "dec_region_check_off":       on("sf_reg_decoder.sv", lambda t: sub(t, r"else if \(region_status != sf_albion_pkg::SF_ST_OKAY\) status_o = region_status;", "else if (1'b0) status_o = region_status;")),
        "dec_lane_mask_short":        on("sf_reg_decoder.sv", lambda t: sub(t, r"if \(word_hit\[0\]\) covered = covered \| 16'h00ff;", "if (word_hit[0]) covered = covered | 16'h000f;")),
        "dec_wrong_word":             on("sf_reg_decoder.sv", lambda t: sub(t, r"assign word_hit\[0\] = \(addr\[63:4\] ==", "assign word_hit[0] = (addr[63:5] ==")),
        # ---- bank storage / side effects
        "bank_side_effect_on_error":  on("sf_reg_bank.sv", lambda t: sub(t, r"assign wr_commit = acc_valid && \(acc_status == sf_albion_pkg::SF_ST_OKAY\) && acc_is_write;", "assign wr_commit = acc_valid && acc_is_write;")),
        "bank_gate_ignored":          on("sf_reg_bank.sv", lambda t: sub(t, r"assign gate_fail = [^;]+;", "assign gate_fail = 1'b0;")),
        "bank_no_lane_mask_on_read":  on("sf_reg_bank.sv", lambda t: sub(t, r"assign acc_rdata = rd_raw & be_mask;", "assign acc_rdata = rd_raw;")),
        "bank_byte_enable_ignored":   on("sf_reg_bank.sv", lambda t: sub(t, rf"(assign {R('ks_a_rwmix')}_wmask = )\{{[^;]+\}};", r"\g<1>32'hffffffff;")),
        "bank_reset_value_wrong":     on("sf_reg_bank.sv", lambda t: sub(t, rf"if \(!rst_ni\) {R('ks_a_rwmix')}_f_hw_q <= 8'h11;", f"if (!rst_ni) {R('ks_a_rwmix')}_f_hw_q <= 8'h10;")),
        "bank_rw_precedence_flipped": on("sf_reg_bank.sv", lambda t: sub(t, rf"(\n    else if \(ks_a_rwmix_f_hw_hw_we_i\[0 \+: 1\]\) {R('ks_a_rwmix')}_f_hw_q <= [^;]+;)(\n    else if \({R('ks_a_rwmix')}_wr && \(\|{R('ks_a_rwmix')}_f_hw_wm\)\) {R('ks_a_rwmix')}_f_hw_q <= [^;]+;)", r"\2\1")),
        "bank_w1c_precedence_flipped": on("sf_reg_bank.sv", lambda t: sub(t, rf"{R('ks_a_flags')}_c_hw_q <= \(\({R('ks_a_flags')}_c_hw_q & ~(\([^;]*?\))\) \| (ks_a_flags_c_hw_set_i\[0 \+: 4\])\);", rf"{R('ks_a_flags')}_c_hw_q <= (({R('ks_a_flags')}_c_hw_q | \2) & ~\1);")),
        "bank_w1s_precedence_flipped": on("sf_reg_bank.sv", lambda t: sub(t, rf"{R('ks_a_flags')}_s_hw_q <= \(\({R('ks_a_flags')}_s_hw_q \| (\([^;]*?\))\) & ~(ks_a_flags_s_hw_clr_i\[0 \+: 4\])\);", rf"{R('ks_a_flags')}_s_hw_q <= (({R('ks_a_flags')}_s_hw_q & ~\2) | \1);")),
        "bank_w1c_clears_zeros":      on("sf_reg_bank.sv", lambda t: sub(t, rf"{R('ks_a_flags')}_c_none_q <= \({R('ks_a_flags')}_c_none_q & ~\(\{{4\{{{R('ks_a_flags')}_wr\}}\}} & {R('ks_a_flags')}_c_none_wb & {R('ks_a_flags')}_c_none_wm\)\);", f"{R('ks_a_flags')}_c_none_q <= ({R('ks_a_flags')}_c_none_q & ~({{4{{{R('ks_a_flags')}_wr}}}} & ~{R('ks_a_flags')}_c_none_wb & {R('ks_a_flags')}_c_none_wm));")),
        "bank_pulse_is_sticky":       on("sf_reg_bank.sv", lambda t: sub(t, rf"else ({R('ks_a_cmd')}_go_pulse_q) <= ([^;]+);", r"else \1 <= \1 | \2;")),
        "bank_wr_strobe_fires_on_read": on("sf_reg_bank.sv", lambda t: sub(t, rf"else ({R('ks_a_both')}_wr_q) <= {R('ks_a_both')}_wr;", rf"else \1 <= {R('ks_a_both')}_wr | {R('ks_a_both')}_rd;")),
        "bank_rd_strobe_fires_on_write": on("sf_reg_bank.sv", lambda t: sub(t, rf"else ({R('ks_a_both')}_rd_q) <= {R('ks_a_both')}_rd;", rf"else \1 <= {R('ks_a_both')}_rd | {R('ks_a_both')}_wr;")),
        "bank_wr_strobe_missing":      on("sf_reg_bank.sv", lambda t: sub(t, rf"else ({R('ks_a_cmd')}_wr_q) <= {R('ks_a_cmd')}_wr;", rf"else \1 <= 1'b0;")),
        "bank_ro_update_ignores_hw":  on("sf_reg_bank.sv", lambda t: sub(t, rf"else if \(ks_a_status_latch_hw_we_i\[0 \+: 1\]\) ({R('ks_a_status')}_latch_q) <= [^;]+;", rf"else if (1'b0) \1 <= 8'h00;")),
        "bank_field_misplaced":       on("sf_reg_bank.sv", lambda t: sub(t, rf"{R('ks_a_rwmix')}_rdata\[0 \+: 8\] = {R('ks_a_rwmix')}_f_hw_q;", f"{R('ks_a_rwmix')}_rdata[1 +: 8] = {R('ks_a_rwmix')}_f_hw_q;")),
        "bank_irq_term_dropped":      on("sf_reg_bank.sv", lambda t: drop_last_or_term(t, "ks_a_irq_o")),
        "bank_async_reset_removed":   on("sf_reg_bank.sv", lambda t: sub(t, rf"always_ff @\(posedge clk_i or negedge rst_ni\) begin\n    if \(!rst_ni\) {R('ks_a_rwmix')}_f_hw_q", f"always_ff @(posedge clk_i) begin\n    if (!rst_ni) {R('ks_a_rwmix')}_f_hw_q")),
    }
    return M




@need("verilator")
class Mutation(TmpCase):
    def run_mutant(self, name):
        m = model(KS_DEF)
        wd = os.path.join(self.tmp, name)
        try:
            r = simflow.simulate(m, wd, seed=1, cycles=4000, mutate=mutants(m)[name])
        except AssertionError as e:
            return name, "BADPATTERN", str(e)
        return name, ("DETECTED" if not r.passed and r.stage == "run" else "SURVIVED" if r.passed else "BUILDFAIL"), r.log[-300:]

    def test_baseline_is_clean(self):
        r = simflow.simulate(model(KS_DEF), os.path.join(self.tmp, "base"), seed=1, cycles=4000)
        self.assertTrue(r.passed, r.log)

    def test_all_mutants_are_detected(self):
        with ThreadPoolExecutor(max_workers=4) as ex:
            res = list(ex.map(self.run_mutant, sorted(mutants(model(KS_DEF)))))
        bad = [(n, s, l) for n, s, l in res if s != "DETECTED"]
        self.assertEqual(bad, [], "mutants not detected:\n" + "\n".join(f"{n}: {s}\n{l}" for n, s, l in bad))
        print(f"\nmutation: {len(res)}/{len(res)} injected bugs detected")


if __name__ == "__main__":
    unittest.main()
