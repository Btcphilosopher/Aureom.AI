"""The same address map, widths, resets and field layouts come out of the RTL package, the C header, the Rust
module and the documentation -- compared with the model and with each other."""

import os
import re
import unittest

from helpers import GENERATED, KS_DEF, SOC_DEF, TmpCase, model, need, run
from albion_reggen.generate import build_outputs


def write_tree(m, d):
    for rel, text in build_outputs(m).items():
        p = os.path.join(d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").write(text)


def reg_name(i):
    return i.reg.name if i.reg.count == 1 else f"{i.reg.name}_{i.elem}"


def expected_regs(m):
    return {(i.periph.name, reg_name(i)): (i.addr, i.reg.width, i.reg.reset) for i in m.instances}


def expected_fields(m):
    out = {}
    for p in m.peripherals:
        for r in p.registers:
            for f in r.fields:
                out[(p.name, r.name, f.name)] = (f.lsb, f.width, f.mask, f.reset)
    return out


class CrossLanguage(TmpCase):
    # ------------------------------------------------------------------ C
    @need("gcc")
    def c_dump(self, m, d):
        src = ['#include <stdio.h>', '#include "sf_regs.h"', "int main(void) {"]
        src.append('#define X(p, n, a, w, r) printf("REG %s %s 0x%llx %d 0x%llx\\n", #p, #n, (unsigned long long)(a), (int)(w), (unsigned long long)(r));')
        src.append("    SF_REGS_REG_LIST(X)")
        src.append("#undef X")
        src.append('#define P(n, b, s) printf("PERIPH %s 0x%llx 0x%llx\\n", #n, (unsigned long long)(b), (unsigned long long)(s));')
        src.append("    SF_REGS_PERIPH_LIST(P)")
        src.append("#undef P")
        src.append('    printf("HASH 0x%016llx\\n", (unsigned long long)SF_REGS_MAP_HASH);')
        for p in m.peripherals:
            for r in p.registers:
                mac = f"SF_{p.name.upper()}_{r.name}"
                src.append(f'    printf("RWMASK {p.name} {r.name} 0x%llx\\n", (unsigned long long){mac}_RW_MASK);')
                for f in r.fields:
                    fm = f"{mac}_{f.name}"
                    src.append(f'    printf("FIELD {p.name} {r.name} {f.name} %u %u 0x%llx 0x%llx\\n", (unsigned){fm}_SHIFT, (unsigned){fm}_WIDTH, '
                               f'(unsigned long long){fm}_MASK, (unsigned long long){fm}_RESET);')
        src.append("    return 0;\n}")
        c = os.path.join(d, "dump.c")
        open(c, "w").write("\n".join(src))
        exe = os.path.join(d, "dump_c")
        r = run(["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I", os.path.join(d, "fw", "c"), c, "-o", exe])
        self.assertEqual(r.returncode, 0, r.stderr)
        return run([exe]).stdout

    # ---------------------------------------------------------------- Rust
    @need("rustc")
    def rust_dump(self, m, d):
        L = ["#[path = \"%s\"] mod regs;" % os.path.join(d, "fw", "rust", "sf_regs.rs"), "fn main() {",
             '    for r in regs::REGS { println!("REG {} {} 0x{:x} {} 0x{:x}", r.periph, r.name, r.addr, r.width, r.reset); }',
             '    for p in regs::PERIPHS { println!("PERIPH {} 0x{:x} 0x{:x}", p.name, p.base, p.size); }',
             '    println!("HASH 0x{:016x}", regs::MAP_HASH);']
        for p in m.peripherals:
            for r in p.registers:
                path = f"regs::{p.name}::{r.name.lower()}"
                L.append(f'    println!("RWMASK {p.name} {r.name} 0x{{:x}}", {path}::RW_MASK as u64);')
                L.append(f'    println!("ADDR {p.name} {r.name} 0x{{:x}} 0x{{:x}} {{}}", {path}::ADDR, {path}::OFFSET, {path}::WIDTH);')
                if r.count > 1:
                    L.append(f'    println!("ARRAY {p.name} {r.name} {{}} {{}} 0x{{:x}} 0x{{:x}}", {path}::COUNT, {path}::STRIDE, {path}::addr(0).unwrap(), {path}::addr({r.count - 1}).unwrap());')
                for f in r.fields:
                    fm = f"{path}::fields::{f.name.lower()}"
                    L.append(f'    println!("FIELD {p.name} {r.name} {f.name} {{}} {{}} 0x{{:x}} 0x{{:x}}", {fm}::SHIFT, {fm}::WIDTH, {fm}::MASK as u64, {fm}::RESET as u64);')
        L.append("}")
        rs = os.path.join(d, "dump.rs")
        open(rs, "w").write("\n".join(L))
        exe = os.path.join(d, "dump_rs")
        r = run(["rustc", "--edition", "2021", "-D", "warnings", "-o", exe, rs])
        self.assertEqual(r.returncode, 0, r.stderr)
        return run([exe]).stdout

    # ------------------------------------------------------------------ SV
    @need("verilator")
    def sv_dump(self, m, d):
        T = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "third_party", "albioncore")
        r = run(["verilator", "--binary", "--timing", "-Wno-fatal", "-Wno-lint", "-Wno-style", "--top-module", "tb_addr_dump",
                 "-Mdir", os.path.join(d, "svobj"), os.path.join(T, "sf_albion_pkg.sv"),
                 os.path.join(d, "rtl", "sf_reg_pkg.sv"), os.path.join(d, "verif", "tb_addr_dump.sv")])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return run([os.path.join(d, "svobj", "Vtb_addr_dump")]).stdout

    # ---------------------------------------------------------------- parse
    @staticmethod
    def parse_regs(text, tag="REG"):
        out = {}
        for ln in text.splitlines():
            t = ln.split()
            if t and t[0] == tag:
                out[(t[1], t[2])] = (int(t[3], 16), int(t[4]), int(t[5], 16))
        return out

    @staticmethod
    def parse_fields(text):
        out = {}
        for ln in text.splitlines():
            t = ln.split()
            if t and t[0] == "FIELD":
                out[(t[1], t[2], t[3])] = (int(t[4]), int(t[5]), int(t[6], 16), int(t[7], 16))
        return out

    def check_one(self, path):
        m = model(path)
        d = self.tmp
        write_tree(m, d)
        want_regs = expected_regs(m)
        want_fields = expected_fields(m)
        want_periph = {p.name: (p.base, p.size) for p in m.peripherals}
        results = {}

        c = self.c_dump(m, d)
        results["C"] = c
        self.assertEqual(self.parse_regs(c), want_regs, "C register table")
        self.assertEqual(self.parse_fields(c), want_fields, "C field macros")
        self.assertEqual({k: (int(a, 16), int(b, 16)) for k, a, b in
                          (ln.split()[1:4] for ln in c.splitlines() if ln.startswith("PERIPH"))}, want_periph)
        self.assertIn(f"HASH 0x{m.hash64:016x}", c)
        for ln in c.splitlines():
            if ln.startswith("RWMASK"):
                _, p, r, v = ln.split()
                reg = next(x for x in m.periph(p).registers if x.name == r)
                self.assertEqual(int(v, 16), reg.mask_of("rw"), f"RW_MASK {p}.{r}")

        rs = self.rust_dump(m, d)
        self.assertEqual(self.parse_regs(rs), want_regs, "Rust register table")
        self.assertEqual(self.parse_fields(rs), want_fields, "Rust field consts")
        self.assertEqual({k: (int(a, 16), int(b, 16)) for k, a, b in
                          (ln.split()[1:4] for ln in rs.splitlines() if ln.startswith("PERIPH"))}, want_periph)
        self.assertIn(f"HASH 0x{m.hash64:016x}", rs)
        # Rust per-register constants agree with the table, array bounds included
        for ln in rs.splitlines():
            t = ln.split()
            if t and t[0] == "ADDR":
                reg = next(x for x in m.periph(t[1]).registers if x.name == t[2])
                p = m.periph(t[1])
                self.assertEqual((int(t[3], 16), int(t[4], 16), int(t[5])), (p.base + reg.offset, reg.offset, reg.width))
            if t and t[0] == "ARRAY":
                reg = next(x for x in m.periph(t[1]).registers if x.name == t[2])
                p = m.periph(t[1])
                self.assertEqual((int(t[3]), int(t[4]), int(t[5], 16), int(t[6], 16)),
                                 (reg.count, reg.stride, p.base + reg.offset, p.base + reg.offset + (reg.count - 1) * reg.stride))

        sv = self.sv_dump(m, d)
        sv_regs = {}
        for ln in sv.splitlines():
            t = ln.split()
            if t and t[0] == "SV_REG":
                sv_regs[t[1]] = (int(t[2], 16), int(t[3]), int(t[4], 16))
        self.assertEqual(sv_regs, {i.name: (i.addr, i.reg.width, i.reg.reset) for i in m.instances}, "SV package")
        self.assertIn(f"SV_MAP_HASH {m.hash64:016x}", sv)
        sv_p = {t[1]: (int(t[2], 16), int(t[3], 16)) for t in (ln.split() for ln in sv.splitlines()) if t and t[0] == "SV_PERIPH"}
        self.assertEqual(sv_p, want_periph)

        # documentation tables
        mm = open(os.path.join(d, "docs", "MEMORY_MAP.md")).read()
        doc_regs = {}
        for ln in mm.splitlines():
            mt = re.match(r"\| `(0x[0-9a-f]+)`(?: \.\. `0x[0-9a-f]+`)? \| `(\w+)` \| `(\w+)(?:\[0\.\.(\d+)\])?`(?: \(stride (\d+)\))? \| (\d+) \| (`0x[0-9a-f]+`|live|-) \|", ln)
            if mt:
                a, p, r, last, stride, w, rst = mt.groups()
                rst = rst.strip("`")
                rst = "0x0" if rst in ("live", "-") else rst
                n = int(last) + 1 if last else 1
                for e in range(n):
                    nm = r if not last else f"{r}_{e}"
                    doc_regs[(p, nm)] = (int(a, 16) + e * (int(stride) if stride else 0), int(w), int(rst, 16))
        self.assertEqual(doc_regs, want_regs, "MEMORY_MAP.md")
        rv = open(os.path.join(d, "docs", "RESET_VALUES.md")).read()
        doc_rst = {}
        for ln in rv.splitlines():
            mt = re.match(r"\| `(0x[0-9a-f]+)` \| `(\w+)\.(\w+?)(?:\[(\d+)\])?` \| (`0x[0-9a-f]+`|live|-) \|", ln)
            if mt:
                a, p, r, e, rst = mt.groups()
                rst = rst.strip("`")
                rst = "0x0" if rst in ("live", "-") else rst
                doc_rst[(p, r if e is None else f"{r}_{e}")] = (int(a, 16), int(rst, 16))
        self.assertEqual(doc_rst, {k: (v[0], v[2]) for k, v in want_regs.items()}, "RESET_VALUES.md")

        # field tables of REGISTERS.md
        regdoc = open(os.path.join(d, "docs", "REGISTERS.md")).read()
        sections = re.split(r"\n### `", regdoc)[1:]
        seen = set()
        for sec in sections:
            head, _, body = sec.partition("`\n")
            p, _, rn = head.partition(".")
            rn = re.sub(r"\[.*\]$", "", rn)
            reg = next(x for x in m.periph(p).registers if x.name == rn)
            rows = re.findall(r"^\| \[(\d+)(?::(\d+))?\] \| (`\w+`|\*reserved\*) \|", body, re.M)
            doc_f = {(n.strip("`"), int(a), int(b) if b else int(a)) for a, b, n in rows if n != "*reserved*"}
            self.assertEqual(doc_f, {(f.name, f.msb, f.lsb) for f in reg.fields}, f"REGISTERS.md fields of {head}")
            n_res = sum(1 for a, b, n in rows if n == "*reserved*")
            cov, runs, pos = reg.field_mask, 0, 0
            while pos < reg.width:
                if (cov >> pos) & 1:
                    pos += 1
                    continue
                runs += 1
                while pos < reg.width and not (cov >> pos) & 1:
                    pos += 1
            self.assertEqual(n_res, runs, f"reserved ranges of {head}")
            seen.add((p, rn))
        self.assertEqual(seen, {(p.name, r.name) for p in m.peripherals for r in p.registers})
        return results

    def test_silicaflux_map(self):
        self.check_one(SOC_DEF)

    def test_kitchen_sink_map(self):
        self.check_one(KS_DEF)

    def test_committed_outputs_match_too(self):
        """The checked-in generated/ tree carries the same numbers as a fresh generation."""
        m = model(SOC_DEF)
        text = open(os.path.join(GENERATED, "fw", "c", "sf_regs.h")).read()
        for i in m.instances:
            self.assertIn(f"{i.addr:x}", text)


if __name__ == "__main__":
    unittest.main()
