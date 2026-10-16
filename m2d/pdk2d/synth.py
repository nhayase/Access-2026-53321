"""
End-to-end synthesis flow: Amaranth design -> MoS2 mapped netlist + report.

Everything runs from pip-installable Python packages only:

  1. Amaranth emits RTLIL;
  2. yowasp-yosys (WASM Yosys) lowers it to primitive gates
     ($_AND_/$_OR_/$_NOT_/$_XOR_/$_MUX_/$_DFF_P_ ...); flip-flops with
     synchronous initialization are legalized to plain $_DFF_P_ because the
     2D library provides only DFFHQ, a reset-less positive-edge D flip-flop;
  3. the pure-Python mapper covers the gate network with the 25-cell
     2D NMOS library (`techmap`), verified by bit-parallel random simulation;
  4. buffer trees enforce the paper's fan-out limit (`legalize_fanout`),
     followed by re-verification;
  5. `analyze` produces timing / depth / power numbers and design-rule
     checks against the published RV32-WUJI constraints.
"""

import contextlib
import json
import os
import time

from amaranth.back import rtlil

from .techmap import read_yosys_json, techmap, verify_equivalence, \
                     legalize_fanout
from .analyze import analyze
from .cells import CONSTRAINTS


__all__ = ["synthesize", "SynthesisFlow", "write_netlist_json"]


_YOSYS_SCRIPT = """\
read_rtlil {name}.il
hierarchy -top {top}
proc
flatten
opt -full
techmap
opt -full
simplemap
opt -full
dfflegalize -cell $_DFF_P_ 01
techmap
simplemap
opt_expr
opt_clean -purge
stat
write_json {name}_gates.json
"""


def _run_yosys(args):
    from yowasp_yosys import run_yosys
    rc = run_yosys(args)
    if rc != 0:
        raise RuntimeError(f"yosys failed with exit code {rc}")


class SynthesisFlow:
    def __init__(self, design, name="m2d", build_dir="build",
                 constraints=CONSTRAINTS):
        self.design      = design
        self.name        = name
        self.build_dir   = build_dir
        self.constraints = constraints
        self.gnet        = None      # primitive gate netlist
        self.mapped      = None      # library-mapped netlist
        self.result      = None      # AnalysisResult
        self.pipelined   = None      # PipelineResult (see pipeline())
        self.pipelined_result = None # AnalysisResult of the physical netlist
        self.log         = []

    def _note(self, msg):
        self.log.append(msg)
        print(f"[pdk2d] {msg}")

    def run(self, verify=True, fix_fanout=True, patterns=8192):
        os.makedirs(self.build_dir, exist_ok=True)
        t0 = time.perf_counter()

        # 1. Amaranth -> RTLIL
        il = rtlil.convert(self.design, name=self.name)
        il_path = os.path.join(self.build_dir, f"{self.name}.il")
        with open(il_path, "w") as f:
            f.write(il)
        self._note(f"RTLIL written to {il_path}")

        # 2. Yosys gate-level lowering (WASM sandbox needs relative paths)
        script = _YOSYS_SCRIPT.format(name=self.name, top=self.name)
        with open(os.path.join(self.build_dir, f"{self.name}.ys"), "w") as f:
            f.write(script)
        cwd = os.getcwd()
        os.chdir(self.build_dir)
        try:
            _run_yosys(["-q", "-p", script.replace("\n", "; ")])
        finally:
            os.chdir(cwd)
        self._note("yosys gate-level lowering done")

        # 3. read + technology map
        self.gnet = read_yosys_json(
            os.path.join(self.build_dir, f"{self.name}_gates.json"),
            top=self.name)
        self._note(f"primitive gates: {len(self.gnet.gates)}")
        self.mapped = techmap(self.gnet)
        self._note(f"mapped cells: {len(self.mapped.gates)} "
                   f"({self.mapped.transistors()} transistors)")

        if verify:
            n = verify_equivalence(self.gnet, self.mapped, patterns=patterns)
            self._note(f"equivalence vs. pre-map netlist: OK "
                       f"({n} random patterns)")

        # 4. fan-out legalization (even-level inverter trees)
        self.prebuffer = analyze(self.mapped, self.constraints)
        if fix_fanout:
            n = legalize_fanout(self.mapped, self.constraints.max_fanout)
            self._note(f"fan-out legalization: {n} buffer inverters inserted")
            if verify and n:
                verify_equivalence(self.gnet, self.mapped, patterns=patterns)
                self._note("equivalence after buffering: OK")

        # 5. analysis + DRC
        self.result = analyze(self.mapped, self.constraints)
        if fix_fanout:
            self.result.notes.append(
                f"logic depth before fan-out buffering: "
                f"{self.prebuffer.logic_depth} stages "
                f"({self.result.logic_depth - self.prebuffer.logic_depth} "
                f"stages added by buffer inverter trees)")
        self._note(f"flow completed in {time.perf_counter() - t0:.2f} s")

        # persist the mapped netlist
        json_path = os.path.join(self.build_dir, f"{self.name}_mapped.json")
        write_netlist_json(self.mapped, json_path, name=self.name)
        self._note(f"mapped netlist written to {json_path}")
        return self.result

    def pipeline(self, verify=True, patterns=4096, holdless=True):
        """Sub-cycle pipelining of the mapped netlist into a depth-compliant
        physical netlist (see `m2d.pdk2d.pipeline`): real DFFHQ insertion,
        hold multiplexers, ring counter; analyzed with the same DRC/timing
        flow and checked for sequential equivalence against the mapped
        netlist.  Sets `self.pipelined` (PipelineResult) and
        `self.pipelined_result` (AnalysisResult); returns the latter."""
        from .pipeline import subcycle_pipeline, verify_subcycle, read_ports
        if self.mapped is None:
            raise RuntimeError("run() first")
        ports = read_ports(os.path.join(self.build_dir,
                                        f"{self.name}_gates.json"), self.name)
        t0 = time.perf_counter()
        self.pipelined = subcycle_pipeline(self.mapped, ports,
                                           constraints=self.constraints,
                                           holdless=holdless)
        pr = self.pipelined
        self._note(f"sub-cycle pipelining: {pr.notes[0]}")
        self.pipelined_result = analyze(pr.netlist, self.constraints)
        r = self.pipelined_result
        self._note(f"physical netlist: {r.transistors} transistors, depth "
                   f"{r.logic_depth} ({'PASS' if r.depth_ok else 'FAIL'}), "
                   f"fan-out {'PASS' if r.fanout_ok else 'FAIL'}")
        if verify:
            n = verify_subcycle(self.mapped, pr, ports, patterns=patterns)
            self._note(f"sequential equivalence over {pr.subcycles} "
                       f"periods vs. mapped netlist: OK ({n} random cases)")
        r.notes.append(pr.notes[0])
        r.notes.append(f"one architectural cycle = {pr.subcycles} physical "
                       f"clock periods; the timing above is per period")
        json_path = os.path.join(self.build_dir,
                                 f"{self.name}_pipelined.json")
        write_netlist_json(pr.netlist, json_path, name=pr.netlist.name)
        self._note(f"physical netlist written to {json_path} "
                   f"({time.perf_counter() - t0:.2f} s)")
        return r


def write_netlist_json(nl, path, name=None):
    """Persist a netlist (mapped or physical) as JSON; `read_mapped_json`
    reads it back."""
    out = {
        "name": name or nl.name,
        "cells": [
            {"kind": k, "ins": [str(x) for x in i], "out": str(o),
             **({"clk": str(c)} if c is not None else {})}
            for k, i, o, c in nl.gates.values()
        ],
        "inputs":  [str(x) for x in sorted(nl.inputs,  key=str)],
        "outputs": [str(x) for x in sorted(nl.outputs, key=str)],
    }
    with open(path, "w") as f:
        json.dump(out, f, indent=1)


def synthesize(design, name="m2d", build_dir="build", **kw):
    flow = SynthesisFlow(design, name=name, build_dir=build_dir)
    flow.run(**kw)
    return flow
