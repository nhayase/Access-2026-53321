#!/usr/bin/env python3
"""Synthesize (a) the external digit-serial register file alone and (b) the
core with the register file integrated into one netlist, at every design
point, through the same pdk2d flow as the core.  Writes results/rf_system.json
and results/rf_system.md.

The integrated netlist gives the system transistor count T_sys and the true
critical path of core + register file in series (the register file read is
combinational from the core's rs1/rs2/index registers through the read
multiplexers into the digit ALU).
"""
import json, os, sys, time
from amaranth import Module
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out
from m2d.core import M2D
from m2d.units.regfile import SerialRegisterFile
from m2d.pdk2d.synth import synthesize

POINTS = [(1, "ripple"), (2, "ripple"), (4, "ripple"), (8, "ripple"), (16, "ripple"),
          (32, "ripple"), (8, "prefix"), (16, "prefix"), (32, "prefix")]


class CoreWithRF(wiring.Component):
    """M2D core with the register file on the same die; memories stay external."""

    def __init__(self, width, adder):
        self.width, self.adder = width, adder
        super().__init__({
            "ibus_addr": Out(32), "ibus_cyc": Out(1), "ibus_ack": In(1), "ibus_rdat": In(32),
            "dbus_addr": Out(32), "dbus_cyc": Out(1), "dbus_we": Out(1), "dbus_sel": Out(4),
            "dbus_wdat": Out(32), "dbus_ack": In(1), "dbus_rdat": In(32),
        })

    def elaborate(self, platform):
        m = Module()
        m.submodules.core = core = M2D(width=self.width, adder=self.adder)
        m.submodules.rf = rf = SerialRegisterFile(width=self.width)
        for p in ("ibus_addr", "ibus_cyc", "dbus_addr", "dbus_cyc", "dbus_we", "dbus_sel", "dbus_wdat"):
            m.d.comb += getattr(self, p).eq(getattr(core, p))
        for p in ("ibus_ack", "ibus_rdat", "dbus_ack", "dbus_rdat"):
            m.d.comb += getattr(core, p).eq(getattr(self, p))
        m.d.comb += [
            rf.raddr1.eq(core.rf_raddr1), rf.raddr2.eq(core.rf_raddr2), rf.index.eq(core.rf_index),
            rf.wen.eq(core.rf_wen), rf.waddr.eq(core.rf_waddr), rf.wdig.eq(core.rf_wdig),
            core.rf_rdig1.eq(rf.rdig1), core.rf_rdig2.eq(rf.rdig2),
        ]
        return m


def row_of(flow, **kw):
    r = flow.result
    return dict(cells=sum(r.cell_counts.values()), dff=r.n_seq, transistors=r.transistors,
                depth=r.logic_depth, depth_prebuf=flow.prebuffer.logic_depth,
                fanout_viol=len(r.fanout_violations), delay_us=round(r.delay_us, 1),
                fmax_hz=round(r.fmax_hz, 1), **kw)


def main(build_dir="build_rf", out="results/rf_system.json", only=None):
    rows = json.load(open(out)) if os.path.exists(out) else []
    done = {(r["width"], r["adder"], r["what"]) for r in rows}
    for width, adder in POINTS:
        if only and (width, adder) not in only:
            continue
        if (width, adder, "rf") not in done:
            t = time.time()
            f = synthesize(SerialRegisterFile(width=width), name=f"rf_w{width}", build_dir=build_dir)
            rows.append(row_of(f, width=width, adder=adder, what="rf", seconds=round(time.time() - t, 1)))
            json.dump(rows, open(out, "w"), indent=1)
        if (width, adder, "system") not in done:
            t = time.time()
            f = synthesize(CoreWithRF(width, adder), name=f"sys_w{width}_{adder}", build_dir=build_dir)
            rows.append(row_of(f, width=width, adder=adder, what="system", seconds=round(time.time() - t, 1)))
            json.dump(rows, open(out, "w"), indent=1)
            print(rows[-1], flush=True)
    return rows


if __name__ == "__main__":
    only = None
    if len(sys.argv) > 1:
        only = [(int(a.split(":")[0]), a.split(":")[1]) for a in sys.argv[1:]]
    main(only=only)


def pipeline_all(build_dir="build_rf", out="results/rf_system_pipelined.json", only=None, patterns=512):
    """Depth-compliant (17-stage) sub-cycle pipelining of the integrated netlists."""
    rows = json.load(open(out)) if os.path.exists(out) else []
    done = {(r["width"], r["adder"]) for r in rows}
    for width, adder in POINTS:
        if only and (width, adder) not in only or (width, adder) in done:
            continue
        t = time.time()
        f = synthesize(CoreWithRF(width, adder), name=f"sys_w{width}_{adder}", build_dir=build_dir, verify=False)
        r = f.pipeline(verify=True, patterns=patterns)
        pr = f.pipelined
        rows.append(dict(width=width, adder=adder, S=pr.subcycles, T_c=r.transistors, depth_c=r.logic_depth,
                         depth_ok=r.depth_ok, fanout_ok=r.fanout_ok, cut_regs=pr.n_cut_regs, hold_mux=pr.n_hold_mux,
                         delay_c_us=round(r.delay_us, 1), seq_equiv_patterns=patterns,
                         T=f.result.transistors, seconds=round(time.time() - t, 1)))
        json.dump(rows, open(out, "w"), indent=1)
        print(rows[-1], flush=True)
    return rows
