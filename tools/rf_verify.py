#!/usr/bin/env python3
"""Verification of the integrated core-plus-register-file design (configuration B).

For every design point: (1) the five hand kernels execute on the integrated
RTL against a zero-wait memory; results are asserted equal to the golden ISS
and cycle counts equal to the core-only RTL of study.py; (2) the checksum
kernel executes at gate level on the mapped, fan-out-legalized integrated
netlist, with the result asserted equal to the ISS and the cycles equal to the
RTL.  Writes results/rf_verify.json.
"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from amaranth.sim import Simulator
import study
from study import (WORKLOADS, golden_run, _mem_bench, M32, GateSim, measure_cycles)
from tools.rf_system import CoreWithRF, POINTS
from m2d.pdk2d.synth import synthesize


def rtl_run(width, adder, prog, data, n_insns):
    dut = CoreWithRF(width, adder)
    mem = {i: w & M32 for i, w in enumerate(prog)}; mem.update(data)
    out = {}
    sim = Simulator(dut); sim.add_clock(1e-6)
    sim.add_testbench(_mem_bench(dut, mem, n_insns, out, 0))
    sim.run()
    return out["cycles"], out["mem"]


def gate_run(flow, build_dir, name, prog, data, n_insns):
    mem = {i: w & M32 for i, w in enumerate(prog)}; mem.update(data)
    gs = GateSim(flow.mapped, os.path.join(build_dir, f"{name}_gates.json"), name)
    retired = 0
    for _ in range(2_000_000):
        gs.set_port("ibus_ack", 0); gs.set_port("dbus_ack", 0); gs.eval_comb()
        if gs.get_port("ibus_cyc"):
            addr = gs.get_port("ibus_addr"); gs.set_port("ibus_rdat", mem.get(addr >> 2, 0)); gs.set_port("ibus_ack", 1)
            retired += 1
            if retired > n_insns:
                break
        elif gs.get_port("dbus_cyc"):
            addr = gs.get_port("dbus_addr") >> 2
            if not gs.get_port("dbus_we"):
                gs.set_port("dbus_rdat", mem.get(addr, 0))
            gs.set_port("dbus_ack", 1)
        gs.eval_comb()
        if gs.get_port("dbus_cyc") and gs.get_port("dbus_we"):
            addr = gs.get_port("dbus_addr") >> 2; sel = gs.get_port("dbus_sel"); wdat = gs.get_port("dbus_wdat")
            mask = sum(0xFF << (8 * i) for i in range(4) if sel & (1 << i))
            mem[addr] = (mem.get(addr, 0) & ~mask) | (wdat & mask)
        gs.tick()
    else:
        raise TimeoutError("gate-level simulation did not finish")
    return gs.cycles, mem.get(0x80 >> 2, 0)


def main(build_dir="build_rf", out="results/rf_verify.json", only=None):
    rows = json.load(open(out)) if os.path.exists(out) else []
    done = {(r["width"], r["adder"]) for r in rows}
    goldens = {n: (fn(), golden_run(*[fn()[0], dict(fn()[1])])) for n, fn in WORKLOADS.items()}
    for width, adder in POINTS:
        if only and (width, adder) not in only or (width, adder) in done:
            continue
        t = time.time(); row = dict(width=width, adder=adder, rtl={}, rtl_matches_core=True)
        for name, ((prog, data), (n, ref, *_)) in goldens.items():
            cyc, mem = rtl_run(width, adder, prog, data, n)
            got = mem.get(0x80 >> 2, 0)
            assert got == ref, (name, width, adder, hex(got), hex(ref))
            core_cyc, _ = measure_cycles(prog, data, n, width, adder)
            row["rtl"][name] = dict(cycles=cyc, core_cycles=core_cyc, result_ok=True)
            row["rtl_matches_core"] &= (cyc == core_cyc)
        flow = synthesize(CoreWithRF(width, adder), name=f"sys_w{width}_{adder}", build_dir=build_dir, verify=False)
        (prog, data), (n, ref, *_) = goldens["checksum"]
        gcyc, got = gate_run(flow, build_dir, f"sys_w{width}_{adder}", prog, data, n)
        row["gate"] = dict(cycles=gcyc, rtl_cycles=row["rtl"]["checksum"]["cycles"], result=f"{got:#010x}",
                           result_ok=(got == ref), cycles_ok=(gcyc == row["rtl"]["checksum"]["cycles"]))
        row["seconds"] = round(time.time() - t, 1)
        rows.append(row); json.dump(rows, open(out, "w"), indent=1)
        print({k: v for k, v in row.items() if k != "rtl"}, row["rtl_matches_core"], flush=True)
    return rows


if __name__ == "__main__":
    only = [(int(a.split(":")[0]), a.split(":")[1]) for a in sys.argv[1:]] or None
    main(only=only)
