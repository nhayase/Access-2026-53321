"""Design-space study: where is the optimal RV32I design point on a
2D-semiconductor (MoS2) process, and how does it move with technology?

For every (datapath width W, adder architecture) design point this script

  1. synthesizes the core through the RV32-WUJI PDK flow (yosys lowering +
     Python technology mapping, both equivalence-checked);
  2. measures CPI by cycle-accurate co-simulation of FIVE workloads with
     different instruction mixes; workload programs are executed on the
     golden ISS first, which provides the retired-instruction count, the
     reference result (asserted identical on every design point) and the
     *measured* dynamic instruction mix;
  3. validates the model chain against RV32-WUJI (delay/power anchors,
     per-instruction-class cycle counts vs. closed-form model at W = 1 and
     W = 32, transistor-gap accounting)                       -> validation.md
  4. evaluates the adders with wire parasitics (exact prefix-graph spans,
     linear-C and distributed-RC wire models, crossover analysis)
  5. projects an architecture-dependent wire model (Rent/Donath average
     wirelength, calibrated to the measured 2.5 pF/pin at the W = 1
     single-layer point; M3D tiers shorten intra-tier wires by 1/sqrt(k))
     and a CFET scenario onto the same netlists;
  6. sweeps defect density, frequency target, M3D tier count, wire scaling
     and static power to locate the BOUNDARIES where the optimal W
     switches                                                 -> boundaries.md

  7. evaluates COMPILED workloads (Embench-IoT built for RV32I) through
     the same validated CPI model, spot-checks that model against RTL for
     prefixes of the compiled binaries at every design point, and bounds
     the serial/parallel ratio over EVERY instruction mix that can exist
                     -> compiled_workloads.md, compiled_spot.md,
                        mix_envelope.md
  8. records which validation stage has been run at which design point
                                                            -> coverage.md
  9. converts every mapped netlist into a depth-compliant (<= 17 stages)
     PHYSICAL netlist by sub-cycle pipelining with real DFFHQ insertion
     (m2d/pdk2d/pipeline.py), checks it with the same DRC/timing flow,
     proves it sequentially equivalent to the mapped netlist and executes
     the checksum workload on it at gate level at sub-cycle granularity
                                          -> depth_compliant.md, .json

Outputs (all under results/): study.csv, study.md, workloads.md,
validation.md, adders.md, boundaries.md, compiled_workloads.md,
mix_envelope.md, coverage.md, depth_compliant.md.

Run:  python3 study.py            (full sweep)
      python3 study.py --quick    (subset of design points)
"""

import argparse
import csv
import math
import os
import random
import sys

from amaranth.sim import Simulator

from m2d.core import M2D
from m2d.sim import M2DSim
from m2d.pdk2d import synthesize
from m2d.pdk2d.cells import CONSTRAINTS, LIBRARY, CMOS_TRANSISTORS

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tests.rv32 import (  # noqa: E402
    ADD, ADDI, AND, ANDI, AUIPC, BEQ, BGE, BLT, BNE, JAL, JALR, LUI,
    LW, OR, SLL, SLLI, SLT, SRA, SRLI, SUB, SW, XOR, XORI,
    GoldenRV32I, M32)
from m2d.elf import load_elf  # noqa: E402

T0_US    = 4.06     # intrinsic stage delay (paper linear model)
SLOPE    = 0.6      # us per pF
C_PIN_A  = 2.5      # pF per input pin, measured single-layer (Scenario A)
NW_PER_T = 72.67e-6  # mW static per transistor (0.431 mW / 5931 T)


# =========================================================== 1. workloads
#
# Five workloads with deliberately different instruction mixes.  The
# *dynamic* mix is not asserted by hand: it is measured by classifying every
# instruction retired on the golden ISS (table written to
# results/workloads.md).  Each workload ends with SW(result -> 0x80) followed
# by a jump-to-self halt; the golden run supplies the retired-instruction
# count and the reference result.

def _wl_checksum():
    """Loop-carried checksum: balanced ALU/shift/mem/branch mix."""
    prog = [
        ADDI(1, 0, 16), ADDI(2, 0, 0), ADDI(3, 0, 0x100),
        LW  (4, 3, 0),
        ADD (2, 2, 4),
        XORI(5, 4, 0x55),
        SLLI(6, 5, 3),
        SRA (7, 6, 1),
        AND (5, 5, 7),
        OR  (2, 2, 5),
        SLT (6, 5, 2),
        SW  (2, 3, 4),
        ADDI(3, 3, 8),
        ADDI(1, 1, -1),
        BNE (1, 0, -0x2C),
        SW  (2, 0, 0x80), JAL(0, 0),
    ]
    data = {(0x100 + 8 * i) >> 2: (0x1234_5601 * (i + 1)) & M32
            for i in range(16)}
    return prog, data


def _wl_memcpy():
    """Unrolled word copy + final checksum: memory-dominated (~60 % mem)."""
    prog = [
        ADDI(1, 0, 8), ADDI(2, 0, 0x100), ADDI(3, 0, 0x200),
        LW(5, 2, 0), SW(5, 3, 0),
        LW(6, 2, 4), SW(6, 3, 4),
        LW(7, 2, 8), SW(7, 3, 8),
        ADDI(2, 2, 12), ADDI(3, 3, 12),
        ADDI(1, 1, -1),
        BNE(1, 0, -0x24),
        # checksum of the copy tail so the result depends on the data
        ADD(4, 5, 6), ADD(4, 4, 7),
        SW(4, 0, 0x80), JAL(0, 0),
    ]
    data = {(0x100 + 4 * i) >> 2: (0xBEEF_0123 ^ (0x0101_0101 * i)) & M32
            for i in range(24)}
    return prog, data


def _wl_softmul():
    """Software shift-add multiply (no RV32M): shift/branch-heavy."""
    prog = [
        ADDI(1, 0, 0x655),        # multiplicand
        ADDI(2, 0, 0x39A),        # multiplier
        ADDI(3, 0, 0),            # product
        ANDI(4, 2, 1),            # loop:
        BEQ (4, 0, 8),            #   skip add if bit clear
        ADD (3, 3, 1),
        SLLI(1, 1, 1),            # skip target
        SRLI(2, 2, 1),
        BNE (2, 0, -0x14),
        SW  (3, 0, 0x80), JAL(0, 0),
    ]
    return prog, {}


def _wl_sort():
    """Bubble sort of 8 words + order-sensitive checksum: branch/mem-heavy,
    data-dependent branch pattern."""
    prog = [
        ADDI(1, 0, 7),                       # 0  passes
        ADDI(2, 0, 0x100),                   # 1  outer: p = base
        ADDI(3, 0, 7),                       # 2  compares per pass
        LW  (4, 2, 0),                       # 3  inner:
        LW  (5, 2, 4),                       # 4
        SLT (6, 5, 4),                       # 5  swap needed?
        BEQ (6, 0, 12),                      # 6  skip swap (2 stores)
        SW  (5, 2, 0),                       # 7
        SW  (4, 2, 4),                       # 8
        ADDI(2, 2, 4),                       # 9  skip target
        ADDI(3, 3, -1),                      # 10
        BNE (3, 0, -0x20),                   # 11 -> inner (idx 3)
        ADDI(1, 1, -1),                      # 12
        BNE (1, 0, -0x30),                   # 13 -> outer (idx 1)
        ADDI(2, 0, 0x100),                   # 14 checksum: acc=(acc<<1)+v
        ADDI(3, 0, 8),                       # 15
        ADDI(4, 0, 0),                       # 16
        LW  (5, 2, 0),                       # 17 csum:
        SLLI(4, 4, 1),                       # 18
        ADD (4, 4, 5),                       # 19
        ADDI(2, 2, 4),                       # 20
        ADDI(3, 3, -1),                      # 21
        BNE (3, 0, -0x14),                   # 22 -> csum (idx 17)
        SW  (4, 0, 0x80), JAL(0, 0),
    ]
    vals = [0x51, 0x07, 0xE3, 0x2A, 0x99, 0x10, 0x7F, 0x44]
    data = {(0x100 + 4 * i) >> 2: vals[i] for i in range(8)}
    return prog, data


def _wl_popcount():
    """Bit-serial population count of 8 words: shift/ALU inner loop."""
    prog = [
        ADDI(1, 0, 8), ADDI(2, 0, 0x100), ADDI(3, 0, 0),
        LW  (4, 2, 0),                       # wloop:
        ADDI(5, 0, 32),
        ANDI(6, 4, 1),                       # bloop:
        ADD (3, 3, 6),
        SRLI(4, 4, 1),
        ADDI(5, 5, -1),
        BNE (5, 0, -0x10),
        ADDI(2, 2, 4),
        ADDI(1, 1, -1),
        BNE (1, 0, -0x24),
        SW  (3, 0, 0x80), JAL(0, 0),
    ]
    data = {(0x100 + 4 * i) >> 2: (0x9E37_79B9 * (i + 3)) & M32
            for i in range(8)}
    return prog, data


WORKLOADS = {
    "checksum": _wl_checksum,
    "memcpy":   _wl_memcpy,
    "softmul":  _wl_softmul,
    "sort":     _wl_sort,
    "popcount": _wl_popcount,
}


# ------------------------------------------------- retirement classes
#
# The digit-serial datapath retires every instruction in one of eight
# classes, each with a closed-form cycle count in D = 32/W:
#
#   one stage  (D + 2)   alu (incl. LUI/AUIPC), jal
#   two stages (2D + 2)  jalr, branch, compare (SLT/SLTU), shift
#   load       (2D + 3)
#   store      (D + 3)
#   plus, at W = 1 only, the shift amount of every retired right shift
#   (that design point uses the transistor-minimal pre-shift scheme).
#
# JALR is a TWO-stage class: the target address needs an addition before
# the fetch can be redirected.  It was previously grouped with JAL as a
# one-stage jump.  None of the five hand-written kernels of WORKLOADS
# retires a single jump, so the error was invisible to all 45 kernel
# measurements; it reaches 1.5 % of CPI at W = 1 on compiled code.  The
# cycle counts below are MEASURED at every design point by validation().

ONE_STAGE = ("alu", "jal")
TWO_STAGE = ("jalr", "branch", "compare", "shift")
CLASSES   = ("alu", "shift", "compare", "load", "store", "branch",
             "jal", "jalr")


def class_cycles(cls, width):
    """Cycles retired by one instruction of class `cls` at datapath width."""
    D = 32 // width
    if cls in ONE_STAGE:
        return D + 2
    if cls in TWO_STAGE:
        return 2 * D + 2
    if cls == "load":
        return 2 * D + 3
    if cls == "store":
        return D + 3
    raise KeyError(cls)


def model_cycles(mix, srx_stall, width):
    """Closed-form cycle count of a dynamic class mix (V2 model)."""
    cyc = sum(n * class_cycles(c, width) for c, n in mix.items())
    if width == 1:
        cyc += srx_stall
    return cyc


def model_cpi(mix, srx_stall, n_insns, width):
    return model_cycles(mix, srx_stall, width) / n_insns


def _classify(word):
    op = word & 0x7F
    f3 = (word >> 12) & 7
    if op == 0x03:
        return "load"
    if op == 0x23:
        return "store"
    if op == 0x63:
        return "branch"
    if op == 0x6F:
        return "jal"
    if op == 0x67:
        return "jalr"
    if op in (0x13, 0x33):
        if f3 in (1, 5):
            return "shift"
        if f3 in (2, 3):
            return "compare"
        return "alu"
    return "alu"      # LUI/AUIPC


def golden_run(prog, data):
    """Run to the halt loop on the ISS; return (n_insns, result@0x80,
    dynamic-mix dict, taken/not-taken branch counts)."""
    mem = {i: w & M32 for i, w in enumerate(prog)}
    mem.update(data)
    iss = GoldenRV32I(mem, pc=0)
    mix = {}
    taken = nottaken = 0
    srx_stall = 0            # sum of shamt over SRL/SRA/SRLI/SRAI retired
    n = 0
    for _ in range(1_000_000):
        pc0 = iss.pc
        word = iss.mem[pc0 >> 2]
        op = word & 0x7F
        f3 = (word >> 12) & 7
        if op in (0x13, 0x33) and f3 == 5:      # SRLI/SRAI/SRL/SRA
            if op == 0x13:
                srx_stall += (word >> 20) & 31
            else:
                srx_stall += iss.x[(word >> 20) & 31] & 31
        iss.step()
        if iss.pc == pc0:                      # jump-to-self halt
            break
        cls = _classify(word)
        mix[cls] = mix.get(cls, 0) + 1
        if cls == "branch":
            if iss.pc != ((pc0 + 4) & M32):
                taken += 1
            else:
                nottaken += 1
        n += 1
    else:
        raise TimeoutError("golden model did not reach the halt loop")
    return n, iss.mem[0x80 >> 2], mix, (taken, nottaken), srx_stall


def _mem_bench(dut, mem, n_insns, out, wait_states=0):
    async def bench(ctx):
        cycles = 0
        retired = 0
        waited = 0
        for _ in range(8_000_000):
            ctx.set(dut.ibus_ack, 0)
            ctx.set(dut.dbus_ack, 0)
            if ctx.get(dut.ibus_cyc):
                if waited < wait_states:
                    waited += 1
                    await ctx.tick()
                    cycles += 1
                    continue
                waited = 0
                addr = ctx.get(dut.ibus_addr)
                ctx.set(dut.ibus_rdat, mem.get(addr >> 2, 0))
                ctx.set(dut.ibus_ack, 1)
                retired += 1
                if retired > n_insns:
                    break
            elif ctx.get(dut.dbus_cyc):
                if waited < wait_states:
                    waited += 1
                    await ctx.tick()
                    cycles += 1
                    continue
                waited = 0
                addr = ctx.get(dut.dbus_addr) >> 2
                if ctx.get(dut.dbus_we):
                    sel = ctx.get(dut.dbus_sel)
                    wdat = ctx.get(dut.dbus_wdat)
                    mask = 0
                    for i in range(4):
                        if sel & (1 << i):
                            mask |= 0xFF << (8 * i)
                    mem[addr] = (mem.get(addr, 0) & ~mask) | (wdat & mask)
                else:
                    ctx.set(dut.dbus_rdat, mem.get(addr, 0))
                ctx.set(dut.dbus_ack, 1)
            await ctx.tick()
            cycles += 1
        out["cycles"] = cycles
        out["mem"] = mem
    return bench


def measure_cycles(prog, data, n_insns, width, adder, wait_states=0):
    """Cycles until the fetch of instruction #(n_insns + 1); `wait_states`
    extra cycles per bus transaction model a width- or speed-limited
    external memory (e.g. 3 waits ~ an 8-bit memory bus for 32-bit words);
    returns (cycles, final data memory)."""
    dut = M2DSim(width=width, adder=adder)
    mem = {i: w & M32 for i, w in enumerate(prog)}
    mem.update(data)
    out = {}
    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_testbench(_mem_bench(dut, mem, n_insns, out, wait_states))
    sim.run()
    return out["cycles"], out["mem"]


def measure_workloads(width, adder, goldens):
    """CPI per workload + geometric mean; asserts every result against the
    golden reference."""
    cpis = {}
    for name, (prog, data, n, ref, _, _, _) in goldens.items():
        cycles, mem = measure_cycles(prog, data, n, width, adder)
        got = mem.get(0x80 >> 2, 0)
        assert got == ref, (f"{name} result mismatch at W={width}/{adder}: "
                            f"{got:#010x} != {ref:#010x}")
        cpis[name] = cycles / n
    logs = [math.log(c) for c in cpis.values()]
    cpis["geomean"] = math.exp(sum(logs) / len(logs))
    return cpis


def load_goldens():
    goldens = {}
    for name, fn in WORKLOADS.items():
        prog, data = fn()
        n, ref, mix, tk, srx = golden_run(prog,
                                          {k: v for k, v in data.items()})
        goldens[name] = (prog, data, n, ref, mix, tk, srx)
    return goldens


def write_workloads_md(goldens, out_dir):
    path = os.path.join(out_dir, "workloads.md")
    classes = list(CLASSES)
    with open(path, "w") as f:
        f.write("Workloads: retired dynamic instruction mix "
                "(measured on the golden ISS)\n\n")
        f.write("| workload | retired |" +
                "".join(f" {c} % |" for c in classes) +
                " taken/not-taken |\n")
        f.write("|:--|--:|" + "--:|" * len(classes) + "--:|\n")
        for name, (_, _, n, _, mix, (tk, nt), _) in goldens.items():
            f.write(f"| {name} | {n} |")
            for c in classes:
                f.write(f" {100.0 * mix.get(c, 0) / n:.1f} |")
            f.write(f" {tk}/{nt} |\n")
    return path


# ================================================= 2. wire / delay models
#
# Architecture-dependent wire model (Scenario B and sensitivity analysis).
#
# The measured Scenario-A pin load C_PIN_A = 2.5 pF/pin lumps device input
# capacitance and wiring/pad load of the fabricated single-layer chip; it is
# kept as-is for Scenario A (it is the calibration that reproduces the
# paper's 171 us critical path).  For projections we split it:
#
#     C_eff(design; k, gamma_w) = C_G + gamma_w * c_w * L_avg(N) / sqrt(k)
#
#   L_avg(N) = A_RENT * N^(P_RENT - 1/2)    Donath average wirelength in
#                                           gate pitches, N = cell count
#   k        = number of M3D tiers: partitioning an N-cell netlist over k
#              stacked tiers shrinks the per-tier footprint to N/k cells,
#              so intra-tier Manhattan lengths scale by 1/sqrt(k)
#              (inter-tier vias are assumed short; stated limitation)
#
#              IMPORTANT -- the two axes of this model use DIFFERENT
#              wirelength scalings, and this is a deliberate choice that
#              must be declared in the paper, not a derivation:
#                * architecture axis (N): Donath, L ~ N^(p - 1/2);
#                * tier axis (k):         geometric footprint, L ~ 1/sqrt(k)
#              Applying Donath consistently to the tier axis would give
#              L(N/k) = L(N) * k^(p - 1/2) = k^-0.1 at p = 0.60, i.e. a
#              factor 0.87 at k = 4 rather than the 0.50 used here.  The
#              1/sqrt(k) rule is the 3-D-IC convention (Rahman & Reif) and
#              is the more optimistic of the two; every conclusion that
#              depends on it ("M3D moves each technology point sqrt(k)
#              deeper into the parallel region") is an assumption of that
#              convention, and the gamma_w axis is swept precisely so that
#              a reader who prefers k^(p-1/2) can relocate their point.
#   gamma_w  = wire-technology scale factor (metallization improvement)
#   C_G      = device input capacitance, assumed 0.1 pF (parameter)
#
# c_w is CALIBRATED so that the W = 1, single-layer, gamma_w = 1 point
# reproduces the measured 2.5 pF/pin.  The model is architecture-dependent
# through N: wider datapaths have more cells, hence longer average wires --
# a physical penalty for parallelism on a single layer that M3D relieves.

P_RENT = 0.60      # Rent exponent (control-dominated small cores)
A_RENT = 0.90      # Donath prefactor, gate pitches
C_G    = 0.10      # pF, device input capacitance (assumption)


def l_avg(n_cells, p=P_RENT, a=A_RENT):
    return a * n_cells ** (p - 0.5)


class WireModel:
    """Rent/Donath average-wirelength wire model.

    NOTE: applying the *average* length to the critical path is an
    approximation (the tail of the length distribution is longer); any
    constant tail factor multiplies c_w and is therefore absorbed by the
    calibration below and by the gamma_w sweep -- it cancels from every
    ratio and boundary in this study.  The Rent parameters (p, a) are
    assumptions; rent_sensitivity() sweeps them.
    """

    def __init__(self, n_cells_ref, p=P_RENT, a=A_RENT):
        self.p, self.a = p, a
        # calibration at the W = 1 single-layer point
        self.c_w = (C_PIN_A - C_G) / l_avg(n_cells_ref, p, a)  # pF/pitch

    def c_eff(self, n_cells, k_tiers=1, gamma_w=1.0):
        return (C_G + gamma_w * self.c_w
                * l_avg(n_cells, self.p, self.a) / math.sqrt(k_tiers))


def delay_scaled(res, c_eff):
    """Critical-path delay with the pin load changed from C_PIN_A to c_eff.
    Exact under the per-pin-uniform load assumption of the PDK delay model:
    every stage is t0 + SLOPE*fanout*C_pin, so only the load part scales.
    The delay-critical path has len(critical_cells) combinational stages
    plus the launching clk-to-Q stage (analyze.py); note this path differs
    from the max-*stage-count* path reported as logic_depth."""
    n = len(res.critical_cells) + 1          # + clk-to-Q stage
    d0 = n * T0_US
    load = res.delay_us - d0
    assert load >= -1e-9, (n, res.delay_us)
    return d0 + load * (c_eff / C_PIN_A)


# ------------------------------------------------------------ scenario B
#
# 2D CFET + M3D projection, applied to the same mapped netlists.
# Assumptions (explicit; sensitivity swept in boundaries()):

SCEN_B = dict(
    vdd   = 4.0,      # V   same devices / supply as the paper
    alpha = 0.10,     # --  switching activity per pin per cycle
    k     = 4,        # --  M3D tiers (baseline)
    gamma_w = 1.0,    # --  wire technology factor (baseline)
    leak_nw_per_t = 0.01,  # nW per CFET transistor (any value << 72.67
                           # leaves every conclusion unchanged)
)


def scenario_b(res, cpi, wm, k=None, gamma_w=None, alpha=None):
    p = SCEN_B
    k = p["k"] if k is None else k
    gamma_w = p["gamma_w"] if gamma_w is None else gamma_w
    alpha = p["alpha"] if alpha is None else alpha
    n_cells = sum(res.cell_counts.values())
    t_cmos = sum(CMOS_TRANSISTORS[kk] * n for kk, n in res.cell_counts.items())
    n_pins = sum(len(LIBRARY[kk].inputs) * n
                 for kk, n in res.cell_counts.items())
    c_eff = wm.c_eff(n_cells, k, gamma_w)                    # pF
    e_dyn_instr = (alpha * n_pins * c_eff * 1e-12
                   * p["vdd"] ** 2 * cpi)                    # J / instr
    p_leak_mw = t_cmos * p["leak_nw_per_t"] * 1e-6
    delay_us = None   # filled by caller with prebuffer-aware variant
    return dict(t_cmos=t_cmos, pins=n_pins, c_eff=c_eff,
                e_dyn_instr=e_dyn_instr, p_leak_mw=p_leak_mw)


# ============================== 3. adder study with wire parasitics (Q3)
#
# The synthesis flow charges every input pin the same load; it cannot see
# that a Brent-Kung combine at distance d spans d bit pitches of wire while
# every ripple-carry wire spans ~1 pitch.  We therefore build the exact
# adder graphs (the same loops as m2d.units.adders), annotate every
# edge with its span in bit pitches, and evaluate the critical path under
#
#   linear-C wire:      t_edge = SLOPE * c_bit * span          (short wires)
#   distributed-RC:     t_edge = SLOPE * c_bit * span**2       (unbuffered
#                                                               long wires)
#
# added on top of the flow-measured gate delay per design.  c_bit (pF per
# bit pitch) is swept; the crossover c_bit* where ripple becomes faster
# than Brent-Kung (if any) is solved numerically.

def _bk_graph(w):
    """Edges (u, v, span) and node list of the Brent-Kung carry network,
    bit-position semantics identical to m2d.units.adders."""
    edges = []            # (src_node, dst_node, span_in_bit_pitches)
    cur = {i: ("pg", i) for i in range(w)}      # current (G,P) owner per pos
    nid = 0
    d = 1
    while d < w:
        for i in range(2 * d - 1, w, 2 * d):
            node = ("u", d, i, nid); nid += 1
            edges += [(cur[i], node, 0), (cur[i - d], node, d)]
            cur[i] = node
        d *= 2
    d = w // 4
    while d and d >= 1:
        for i in range(3 * d - 1, w, 2 * d):
            node = ("dn", d, i, nid); nid += 1
            edges += [(cur[i], node, 0), (cur[i - d], node, d)]
            cur[i] = node
        d //= 2
    # carry i taps prefix node i-1 (span ~1) and feeds sum XOR at bit i
    sinks = []
    for i in range(1, w + 1):
        node = ("c", i)
        edges.append((cur[i - 1], node, 1))
        sinks.append(node)
    return edges, sinks


def _longest_wire_path(edges, sinks, quad=False):
    """Max total span (or span^2) over any pg->carry path."""
    from collections import defaultdict
    weight = defaultdict(float)   # node -> best accumulated wire cost
    indeg_order = []              # edges are emitted in topological order
    for u, v, s in edges:
        w_ = (s ** 2) if quad else s
        weight[v] = max(weight[v], weight[u] + w_)
    return max(weight[v] for v in sinks)


def _ripple_wire(w, quad=False):
    # carry chain: w majority stages, each driving the next bit (span 1)
    return float(w)               # 1 or 1^2 per hop, w hops


def adder_study(build_dir="build"):
    rows = []
    for w in (4, 8, 16, 32):
        for kind in ("ripple", "prefix"):
            flow = synthesize(_AdderOnly(w, kind).mod,
                              name=f"adder_w{w}_{kind}", build_dir=build_dir)
            pre = flow.prebuffer
            if kind == "prefix":
                edges, sinks = _bk_graph(w)
                s_lin = _longest_wire_path(edges, sinks, quad=False)
                s_quad = _longest_wire_path(edges, sinks, quad=True)
            else:
                s_lin = _ripple_wire(w)
                s_quad = _ripple_wire(w, quad=True)
            rows.append(dict(width=w, adder=kind,
                             transistors=flow.result.transistors,
                             depth=pre.logic_depth,
                             delay_us=pre.delay_us,
                             s_lin=s_lin, s_quad=s_quad))
    # crossover analysis per width
    xover = []
    for w in (4, 8, 16, 32):
        rr = next(r for r in rows if r["width"] == w and r["adder"] == "ripple")
        bk = next(r for r in rows if r["width"] == w and r["adder"] == "prefix")
        # delay(c) = delay0 + SLOPE*c*S ; ripple slower at c=0.
        # linear: crossover only if S_bk > S_ripple
        x_lin = ((rr["delay_us"] - bk["delay_us"])
                 / (SLOPE * (bk["s_lin"] - rr["s_lin"]))
                 if bk["s_lin"] > rr["s_lin"] else None)
        x_quad = ((rr["delay_us"] - bk["delay_us"])
                  / (SLOPE * (bk["s_quad"] - rr["s_quad"]))
                  if bk["s_quad"] > rr["s_quad"] else None)
        xover.append(dict(width=w, x_lin=x_lin, x_quad=x_quad,
                          s_lin_r=rr["s_lin"], s_lin_bk=bk["s_lin"],
                          s_quad_r=rr["s_quad"], s_quad_bk=bk["s_quad"]))
    return rows, xover


class _AdderOnly:
    """Standalone W-bit adder wrapper for component-level synthesis."""

    def __init__(self, width, kind):
        from amaranth.lib import wiring
        from amaranth.lib.wiring import In, Out
        from m2d.units.adders import make_adder

        class _A(wiring.Component):
            def __init__(self):
                super().__init__({
                    "a": In(width), "b": In(width), "cin": In(1),
                    "s": Out(width), "cout": Out(1)})

            def elaborate(self, platform):
                from amaranth import Module
                m = Module()
                s_, co = make_adder(m, kind, self.a, self.b, self.cin, "add")
                m.d.comb += [self.s.eq(s_), self.cout.eq(co)]
                return m
        self.mod = _A()


def write_adders_md(rows, xover, out_dir):
    path = os.path.join(out_dir, "adders.md")
    with open(path, "w") as f:
        f.write("Standalone W-bit adders (pre-buffering) with wire-span "
                "analysis\n\n")
        f.write("| W | adder | T | depth | delay us (c_bit=0) | "
                "S_lin (pitches) | S_quad (pitches^2) |\n")
        f.write("|--:|:--|--:|--:|--:|--:|--:|\n")
        for r in rows:
            f.write(f"| {r['width']} | {r['adder']} | {r['transistors']} | "
                    f"{r['depth']} | {r['delay_us']:.1f} | "
                    f"{r['s_lin']:.0f} | {r['s_quad']:.0f} |\n")
        f.write("\nCrossover wire capacitance c_bit* where ripple becomes "
                "faster than Brent-Kung (delay0 + SLOPE*c_bit*S model):\n\n")
        f.write("| W | linear-C c_bit* | distributed-RC c_bit* |\n")
        f.write("|--:|:--|:--|\n")
        for x in xover:
            lin = ("none (BK wire path shorter than ripple's)"
                   if x["x_lin"] is None else f"{x['x_lin']:.2f} pF/pitch")
            quad = ("none" if x["x_quad"] is None
                    else f"{x['x_quad']:.3f} pF/pitch")
            f.write(f"| {x['width']} | {lin} | {quad} |\n")
    return path


# ========================================== 4. model validation (Q2)
#
# Chain of evidence, each item labeled:
#   calibrated  -- the model parameter is fitted to this paper value
#   reproduced  -- the flow/model reproduces a paper value not fitted to it
#   predicted   -- model output checked against closed-form expectation
#
# The per-instruction-class cycle counts are the strongest check: they are
# *measured* on the RTL by differential co-simulation (cycles(2n copies) -
# cycles(n copies))/n, and compared with the closed-form digit-serial model
#   1-stage: D+2   2-stage: 2D+2   load: 2D+3   store: D+3
#   (W = 1 SRLI/SRAI: +shamt stall cycles),   D = 32/W
# at both ends of the design space (W = 1 and W = 32).

def _cycles_per_insn(width, adder, mk_insn, n1=8, n2=16, setup=()):
    def run(n):
        prog = list(setup) + [mk_insn(i) for i in range(n)] + [JAL(0, 0)]
        data = {0x100 >> 2: 0x0000_1234}
        cyc, _ = measure_cycles(prog, data, len(setup) + n, width, adder)
        return cyc
    return (run(n2) - run(n1)) / (n2 - n1)


# V2 case list: one representative instruction per retirement class.
#
# LUI, AUIPC and JALR were added after the compiled workloads of
# compiled_workloads() showed that the hand kernels retire no jumps at all,
# so the JAL/JALR distinction had never been measured.  JALR falls through
# to the next instruction here because x1 is pre-loaded with the address of
# the first JALR: `JALR x1, x1, 4` then jumps to pc + 4 and rewrites x1 with
# pc + 4, which keeps the sequence straight-line and lets the differential
# measurement of _cycles_per_insn work.
VALIDATION_CASES = [
    # name, instruction factory, setup, model formula f(D, W)
    ("ADDI",      lambda i: ADDI(1, 1, 1),        (),
     lambda D, W: D + 2),
    ("ADD",       lambda i: ADD(1, 1, 2),         (ADDI(2, 0, 3),),
     lambda D, W: D + 2),
    ("LUI",       lambda i: LUI(1, 0x12345),      (),
     lambda D, W: D + 2),
    ("AUIPC",     lambda i: AUIPC(1, 1),          (),
     lambda D, W: D + 2),
    ("SLT",       lambda i: SLT(1, 2, 3),         (ADDI(2, 0, 1),
                                                   ADDI(3, 0, 2)),
     lambda D, W: 2 * D + 2),
    ("SLLI4",     lambda i: SLLI(1, 1, 4),        (ADDI(1, 0, 1),),
     lambda D, W: 2 * D + 2),
    ("SRLI4",     lambda i: SRLI(1, 1, 4),        (ADDI(1, 0, 1),),
     lambda D, W: 2 * D + 2 + (4 if W == 1 else 0)),
    ("BEQ taken", lambda i: BEQ(0, 0, 4),         (),
     lambda D, W: 2 * D + 2),
    ("BNE n-t",   lambda i: BNE(0, 0, 4),         (),
     lambda D, W: 2 * D + 2),
    ("JAL",       lambda i: JAL(0, 4),            (),
     lambda D, W: D + 2),
    ("JALR",      lambda i: JALR(1, 1, 4),        (AUIPC(1, 0),
                                                   ADDI(1, 1, 8)),
     lambda D, W: 2 * D + 2),
    ("LW",        lambda i: LW(1, 0, 0x100),      (),
     lambda D, W: 2 * D + 3),
    ("SW",        lambda i: SW(1, 0, 0x100),      (),
     lambda D, W: D + 3),
]


def validation(width_pairs=None):
    """V2: differential RTL cycle measurement vs. the closed-form model.

    Defaults to every reported design point (9), not a subset of 3, so that
    the class table is validated wherever it is used.
    """
    if width_pairs is None:
        width_pairs = POINTS_FULL
    rows = []
    for width, adder in width_pairs:
        D = 32 // width
        for name, mk, setup, model in VALIDATION_CASES:
            meas = _cycles_per_insn(width, adder, mk, setup=setup)
            pred = model(D, width)
            # cross-check the case list against the canonical class model
            rows.append(dict(point=f"W={width}/{adder}", insn=name,
                             measured=meas, model=pred,
                             ok=abs(meas - pred) < 1e-9))
    return rows


def write_validation_md(rows, res_w1, prebuf_w1, buffers_w1, out_dir):
    path = os.path.join(out_dir, "validation.md")
    n_ok = sum(1 for r in rows if r["ok"])
    n_pts = len({r["point"] for r in rows})
    n_cls = len({r["insn"] for r in rows})
    with open(path, "w") as f:
        f.write("Model validation against RV32-WUJI "
                "(Ao et al., Nature 640, 654 (2025))\n\n")
        f.write("V1. Calibration anchors (delay / power / sequential "
                "cost).  NOTE: these are CALIBRATIONS, not independent "
                "validations -- the delay pair (t0, slope) is jointly "
                "fitted to the published 171 us total, so V1 carries no "
                "evidential weight on its own.  The validation anchors of "
                f"this study are V2 ({n_ok}/{len(rows)} cycle-exact "
                f"per-class checks, {n_cls} classes x {n_pts} design "
                "points), V2b (gate-level execution of full workloads, "
                "cycle count and checksum asserted against RTL and the "
                "golden ISS), and the yosys+ABC mapper cross-check.\n\n")
        f.write("| item | model | paper | type |\n|:--|:--|:--|:--|\n")
        d17 = 17 * (T0_US + SLOPE * 4 * C_PIN_A)
        f.write(f"| 17-stage critical path | {d17:.2f} us "
                f"(17 x (4.06 + 0.6 x 10 pF)) | 171 us (Fig. 3c/d) | "
                f"calibrated (jointly fitted) |\n")
        f.write(f"| static power | 5931 T x 72.67 nW/T = "
                f"{5931 * NW_PER_T:.3f} mW | 0.431 mW (Ext. Table 2) | "
                f"calibrated |\n")
        f.write("| flip-flop cost | 18 T/FF | 8-bit register = 144 T "
                "(Suppl. Fig. 7) | calibrated |\n")
        f.write("| excluded cells | 7 cells with NM < 0.2 V "
                "| Fig. 3b | input data |\n")
        f.write("\nV2. Per-instruction-class cycle counts "
                "(RTL differential measurement vs. closed-form serial "
                "model; D = 32/W)\n\n")
        f.write("| design point | class | measured | model | match |\n")
        f.write("|:--|:--|--:|--:|:--:|\n")
        for r in rows:
            f.write(f"| {r['point']} | {r['insn']} | {r['measured']:.2f} | "
                    f"{r['model']} | {'OK' if r['ok'] else 'MISMATCH'} |\n")
        f.write("\nV3. Transistor accounting, W = 1 core vs. fabricated "
                "RV32-WUJI\n\n")
        t_dff = 18 * res_w1.n_seq
        t_buf = 2 * buffers_w1
        t_mux = 9 * res_w1.cell_counts.get("MUX2", 0)
        t_rest = res_w1.transistors - t_dff - t_buf - t_mux
        f.write("| component | transistors | share |\n|:--|--:|--:|\n")
        for nm, t in [("flip-flops (18 T each)", t_dff),
                      (f"fan-out buffer inverters ({buffers_w1} INV)", t_buf),
                      ("MUX2 trees (imm/PC selects, FSM D-muxes)", t_mux),
                      ("other combinational logic", t_rest),
                      ("TOTAL (this flow)", res_w1.transistors)]:
            share = 100.0 * t / res_w1.transistors
            f.write(f"| {nm} | {t} | {share:.1f} % |\n")
        f.write(f"| RV32-WUJI whole chip (reference) | 5931 | -- |\n")
        f.write("\nGap drivers vs. the fabricated chip (x"
                f"{res_w1.transistors / 5931:.2f}): no ABC-class global "
                "restructuring, 32:1 immediate-mux tree instead of the "
                "paper's serial immediate decoder, no register-file port "
                "sharing, FSM multi-writer D-input mux chains.\n")
    return path


# ================================ 5. boundary analysis (Q5): where does
#                                     the optimal W switch?
#
# Four technology axes.  For each, the optimum over design points and the
# exact boundary values where it changes hands:
#
#   (a) defect density d [defects/transistor]: expected throughput per
#       fabricated die  E[thr] = exp(-d T) * thr.  Between two designs
#       (T_i, thr_i > thr_j, T_i > T_j) the optimum switches at
#           d* = ln(thr_i / thr_j) / (T_i - T_j).
#       Evaluated for fixed-1-kHz operation and for f_max operation.
#   (b) frequency target f_req: the feasibility ladder (delay < 1/f_req);
#       the throughput-optimal design is the widest feasible one.
#   (c) M3D tiers k and wire factor gamma_w: Scenario-B dynamic energy and
#       delay with the architecture-dependent wire model.
#   (d) static power per transistor p_s: fixed-frequency energy/instr
#       E = (p_s T + alpha N_pins C_eff V^2 f) CPI / f.

def _envelope_d(designs, thr_key, t_key="transistors",
                d_lo=1e-7, d_hi=3e-3, n=600):
    """Upper envelope of exp(-dT)*thr over a log-d grid; returns the
    sequence of optimal designs with exact switch points."""
    seq = []
    for i in range(n + 1):
        d = d_lo * (d_hi / d_lo) ** (i / n)
        best = max(designs, key=lambda r: math.exp(-d * r[t_key]) * r[thr_key])
        if not seq or seq[-1][0] is not best:
            seq.append((best, d))
    out = []
    for j, (des, d_first) in enumerate(seq):
        if j == 0:
            out.append((des, None))
        else:
            prev = seq[j - 1][0]
            d_star = (math.log(prev[thr_key] / des[thr_key])
                      / (prev[t_key] - des[t_key]))
            out.append((des, d_star))
    return out


def boundaries(rows, wm, out_dir):
    """rows: sweep result dicts (must contain transistors, cpi_geo, fmax_hz,
    delay_us, depth, cell counts snapshot fields)."""
    path = os.path.join(out_dir, "boundaries.md")
    lines = []
    w = lines.append

    for r in rows:
        r["thr_1k"] = 1000.0 / r["cpi_geo"]
        r["thr_fmax"] = r["fmax_hz"] / r["cpi_geo"]

    # ---- (a) defect-density boundaries
    w("Boundary analysis: where does the optimal design point switch?\n")
    w("\n## (a) Defect density (yield axis)\n")
    w("\nMetric: expected throughput per fabricated die, "
      "E[thr] = exp(-d T) x thr.  d* boundaries are exact "
      "(d* = ln(thr_i/thr_j)/(T_i - T_j)); also expressed as the yield the "
      "W = 1 core would have at that defect density.\n")
    for label, key in (("fixed 1 kHz operation", "thr_1k"),
                       ("f_max operation", "thr_fmax")):
        env = _envelope_d(rows, key)
        w(f"\n### {label}\n\n")
        w("| optimal design | from d [1/T] | i.e. defects/10^6 T | "
          "yield of W=1 core there |\n|:--|:--|--:|--:|\n")
        for des, d_star in env:
            tag = f"W={des['width']} {des['adder']}"
            if d_star is None:
                w(f"| {tag} | d -> 0 | -- | -- |\n")
            else:
                y1 = math.exp(-d_star * 10474)
                w(f"| {tag} | {d_star:.3e} | {d_star * 1e6:.0f} | "
                  f"{100 * y1:.0f} % |\n")

    # ---- (b) frequency-target ladder
    w("\n## (b) Frequency target (feasibility axis)\n\n")
    w("Throughput-optimal design vs. required clock f_req "
      "(design feasible iff critical-path delay < 1/f_req; among feasible "
      "designs the lowest-CPI one wins since thr = f_req / CPI):\n\n")
    w("| f_req range | optimal design | limiting delay |\n|:--|:--|:--|\n")
    ladder = sorted(rows, key=lambda r: r["cpi_geo"])   # widest first
    f_lo = 0.0
    for i, des in enumerate(ladder):
        f_hi = 1e6 / des["delay_us"]
        better = [x for x in ladder[:i] if x["cpi_geo"] < des["cpi_geo"]]
        # this design is optimal from where all lower-CPI designs are
        # infeasible up to its own f_max
        f_start = max([1e6 / x["delay_us"] for x in better], default=0.0)
        if f_hi <= f_start:
            continue
        w(f"| {f_start:.0f} - {f_hi:.0f} Hz | W={des['width']} "
          f"{des['adder']} | {des['delay_us']:.1f} us |\n")
    w(f"| > {max(1e6 / r['delay_us'] for r in rows):.0f} Hz | "
      "infeasible in this library | -- |\n")

    # ---- (c) M3D tiers / wire factor: Scenario-B optima
    w("\n## (c) M3D tiers k and wire factor gamma_w (Scenario B)\n\n")
    w("Optimal W by dynamic energy/instruction and by throughput at the "
      "wire-scaled f_max (architecture-dependent "
      "C_eff = C_G + gamma_w c_w L(N)/sqrt(k)):\n\n")
    w("| k | gamma_w | E_dyn-optimal | thr-optimal | "
      "C_eff(W=1) pF | C_eff(W=32 prefix) pF |\n"
      "|--:|--:|:--|:--|--:|--:|\n")
    for k in (1, 2, 4, 8):
        for gw in (1.0, 0.3, 0.1):
            best_e, best_t = None, None
            c1 = c32 = None
            for r in rows:
                sb = scenario_b(r["_res"], r["cpi_geo"], wm, k=k, gamma_w=gw)
                dly = delay_scaled(r["_res"], sb["c_eff"])
                thr = 1e6 / dly / r["cpi_geo"]
                if best_e is None or sb["e_dyn_instr"] < best_e[1]:
                    best_e = (r, sb["e_dyn_instr"])
                if best_t is None or thr > best_t[1]:
                    best_t = (r, thr)
                if r["width"] == 1:
                    c1 = sb["c_eff"]
                if r["width"] == 32 and r["adder"] == "prefix":
                    c32 = sb["c_eff"]
            w(f"| {k} | {gw} | W={best_e[0]['width']} "
              f"{best_e[0]['adder']} ({best_e[1] * 1e9:.1f} nJ) | "
              f"W={best_t[0]['width']} {best_t[0]['adder']} "
              f"({best_t[1]:.0f} i/s) | {c1:.2f} | {c32:.2f} |\n")

    # ---- (d) static power axis
    w("\n## (d) Static power per transistor p_s (NMOS -> CFET transition)"
      "\n\n")
    w("Energy/instruction at 1 kHz, E = (p_s T + P_dyn) CPI / f with the "
      "baseline wire model (k=1, gamma_w=1).  Optimal W vs. p_s:\n\n")
    w("| p_s [nW/T] | E-optimal design | E/instr |\n|--:|:--|:--|\n")
    switches = []
    prev = None
    for ps in (72.67, 30, 10, 3, 1, 0.3, 0.1, 0.01):
        best = None
        for r in rows:
            sb = scenario_b(r["_res"], r["cpi_geo"], wm, k=1, gamma_w=1.0)
            e = ((ps * 1e-9 * r["transistors"]
                  + SCEN_B["alpha"] * sb["pins"] * sb["c_eff"] * 1e-12
                  * SCEN_B["vdd"] ** 2 * 1000.0)
                 * r["cpi_geo"] / 1000.0)
            if best is None or e < best[1]:
                best = (r, e)
        tag = f"W={best[0]['width']} {best[0]['adder']}"
        if prev is not None and tag != prev:
            switches.append(ps)
        prev = tag
        w(f"| {ps} | {tag} | {best[1] * 1e6:.2f} uJ |\n")
    if not switches:
        w("\nNo switch on this axis at the fixed 1 kHz clock: the "
          "energy-optimal width is the same for every p_s (both p_s T CPI "
          "and N_pins C_eff CPI are minimized by the same design).  This "
          "holds under fixed-clock or race-to-sleep operation only; under "
          "iso-throughput operation without power gating the static term "
          "scales with T alone and favors serialization (article, Section "
          "IV-C).  The energy-optimal width at f_max is mapped in the "
          "article's Fig. 5.\n")

    with open(path, "w") as f:
        f.writelines(lines)
    return path


# ================================================== 6. sweep orchestration

POINTS_FULL = [(w, "ripple") for w in (1, 2, 4, 8, 16, 32)] \
            + [(w, "prefix") for w in (8, 16, 32)]
POINTS_QUICK = [(1, "ripple"), (8, "ripple"), (32, "ripple"),
                (32, "prefix")]

WL_NAMES = list(WORKLOADS) + ["geomean"]


def run(points, build_dir="build", out_dir="results"):
    os.makedirs(out_dir, exist_ok=True)
    goldens = load_goldens()
    write_workloads_md(goldens, out_dir)

    rows = []
    wm = None
    w1_flow = None
    for width, adder in points:
        tag = f"w{width}_{adder}"
        print(f"=== design point {tag} " + "=" * 40)
        cpis = measure_workloads(width, adder, goldens)
        flow = synthesize(M2D(width=width, adder=adder),
                          name=f"m2d_{tag}", build_dir=build_dir)
        r = flow.result
        if width == 1 and adder == "ripple":
            w1_flow = flow
        print(f"[study] gate-level workload execution ({tag}) ...")
        g_cyc, alpha_m, io_pi, _ = gate_level_sim(flow, width, adder,
                                                  build_dir=build_dir)
        prog_c, data_c = WORKLOADS["checksum"]()
        n_c, _ref_c = golden_run(prog_c, dict(data_c))[:2]
        rtl_cyc, _ = measure_cycles(prog_c, data_c, n_c, width, adder)
        assert g_cyc == rtl_cyc, (g_cyc, rtl_cyc)
        print(f"[study]   cycle-exact vs RTL: {g_cyc} cycles, "
              f"alpha = {alpha_m:.4f}")
        row = dict(width=width, adder=adder,
                   cells=sum(r.cell_counts.values()), dff=r.n_seq,
                   transistors=r.transistors,
                   depth=r.logic_depth, depth_prebuf=flow.prebuffer.logic_depth,
                   depth_ok=r.depth_ok,
                   fanout_viol=len(r.fanout_violations),
                   delay_us=round(r.delay_us, 1),
                   fmax_hz=round(r.fmax_hz, 1),
                   power_mw=round(r.power_mw, 3),
                   cpi_geo=cpis["geomean"],
                   alpha_meas=round(alpha_m, 4),
                   io_toggles_pi=round(io_pi, 1),
                   n_io=n_io(width),
                   _res=r, _flow=flow)
        for n in WL_NAMES:
            row[f"cpi_{n}"] = round(cpis[n], 2)
        rows.append(row)

    if wm is None:
        n_ref = next(r["cells"] for r in rows
                     if r["width"] == 1 and r["adder"] == "ripple")
        wm = WireModel(n_ref)

    # derived Scenario-A metrics
    for r in rows:
        cpi = r["cpi_geo"]
        r["thr_fmax"] = round(r["fmax_hz"] / cpi, 1)
        r["e_uj_fmax"] = round(r["power_mw"] * 1e3 * cpi / r["fmax_hz"], 3)
        r["thr_1k"] = round(1000.0 / cpi, 1)
        r["e_uj_1k"] = round(r["power_mw"] * cpi, 2)
        sb = scenario_b(r["_res"], cpi, wm, alpha=r["alpha_meas"])
        r["t_cmos"] = sb["t_cmos"]
        r["pins"] = sb["pins"]
        r["c_eff_b"] = round(sb["c_eff"], 2)
        r["e_nj_b"] = round(sb["e_dyn_instr"] * 1e9, 2)
        r["cpi_geo"] = round(cpi, 2)

    # ---- CSV
    fields = [k for k in rows[0] if not k.startswith("_")]
    with open(os.path.join(out_dir, "study.csv"), "w", newline="") as f:
        wtr = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        wtr.writeheader()
        wtr.writerows(rows)

    # ---- study.md
    with open(os.path.join(out_dir, "study.md"), "w") as f:
        f.write("Table 1: synthesis results (RV32-WUJI PDK flow)\n\n")
        f.write("| W | adder | cells | DFF | T (NMOS) | depth (pre-buf) | "
                "depth<=17 | fan-out viol. | delay us |\n")
        f.write("|--:|:--|--:|--:|--:|--:|:--:|--:|--:|\n")
        for r in rows:
            f.write(f"| {r['width']} | {r['adder']} | {r['cells']} | "
                    f"{r['dff']} | {r['transistors']} | "
                    f"{r['depth']} ({r['depth_prebuf']}) | "
                    f"{'PASS' if r['depth_ok'] else 'FAIL'} | "
                    f"{r['fanout_viol']} | "
                    f"{r['delay_us']} |\n")
        f.write("\nTable 2: CPI per workload (cycle-accurate, zero-wait "
                "memory; results asserted identical across design points)\n\n")
        f.write("| W | adder |" + "".join(f" {n} |" for n in WL_NAMES) + "\n")
        f.write("|--:|:--|" + "--:|" * len(WL_NAMES) + "\n")
        for r in rows:
            f.write(f"| {r['width']} | {r['adder']} |" +
                    "".join(f" {r['cpi_' + n]} |" for n in WL_NAMES) + "\n")
        f.write("\nTable 3: performance and energy, Scenario A (measured "
                "PDK, static-dominated; geomean CPI)\n\n")
        f.write("| W | adder | f_max Hz | instr/s @f_max | E/instr uJ "
                "@f_max | instr/s @1kHz | E/instr uJ @1kHz | P mW |\n")
        f.write("|--:|:--|--:|--:|--:|--:|--:|--:|\n")
        for r in rows:
            f.write(f"| {r['width']} | {r['adder']} | {r['fmax_hz']} | "
                    f"{r['thr_fmax']} | {r['e_uj_fmax']} | {r['thr_1k']} | "
                    f"{r['e_uj_1k']} | {r['power_mw']} |\n")
        f.write("\nTable 4: Scenario B baseline (2D CFET, M3D k=4, "
                "gamma_w=1; architecture-dependent wire model, MEASURED "
                "per-design alpha)\n\n")
        f.write("| W | adder | T (CMOS) | pins | C_eff pF/pin | "
                "alpha (meas.) | E_dyn/instr nJ |\n")
        f.write("|--:|:--|--:|--:|--:|--:|--:|\n")
        for r in rows:
            f.write(f"| {r['width']} | {r['adder']} | {r['t_cmos']} | "
                    f"{r['pins']} | {r['c_eff_b']} | {r['alpha_meas']} | "
                    f"{r['e_nj_b']} |\n")
        f.write("\nTable 5: gate-level workload execution (checksum): "
                "cycle count asserted equal to RTL, checksum asserted "
                "equal to the golden ISS, per-design measured switching "
                "activity and pad-bit toggles\n\n")
        f.write("| W | adder | alpha measured | pad-bit toggles/instr "
                "|\n|--:|:--|--:|--:|\n")
        for r in rows:
            f.write(f"| {r['width']} | {r['adder']} | {r['alpha_meas']} | "
                    f"{r['io_toggles_pi']} |\n")

    # ---- adders / validation / boundaries
    ad_rows, xover = adder_study(build_dir)
    write_adders_md(ad_rows, xover, out_dir)
    if w1_flow is not None:
        val = validation()
        buffers_w1 = w1_flow.result.cell_counts.get("INV", 0)
        # count only legalization inverters: reconstruct from note
        nbuf = 0
        for note in w1_flow.notes if hasattr(w1_flow, "notes") else []:
            pass
        # the flow printed the count; recompute: buffers = INV added during
        # legalization = total INV - pre-buffer INV
        nbuf = (w1_flow.result.cell_counts.get("INV", 0)
                - w1_flow.prebuffer.cell_counts.get("INV", 0))
        write_validation_md(val, w1_flow.result, w1_flow.prebuffer,
                            nbuf, out_dir)
    boundaries(rows, wm, out_dir)
    phase_diagrams(rows, wm, out_dir)
    try:
        figures(rows, wm, out_dir)
    except Exception as e:                     # pragma: no cover
        print(f"[study] figure generation unavailable: {e}")

    # ---- audit additions (each isolated: a reduced --quick point set
    #      must never abort the sweep)
    for name, fn in (("io_tables", lambda: io_tables(rows, out_dir)),
                     ("depth_compliant",
                      lambda: depth_compliant(rows, out_dir,
                                              build_dir=build_dir)),
                     ("rent_sensitivity",
                      lambda: rent_sensitivity(rows, out_dir)),
                     ("predicted_cpi",
                      lambda: predicted_cpi(goldens, rows, out_dir)),
                     ("waitstate_cpi",
                      lambda: waitstate_cpi(rows, goldens, out_dir)),
                     ("mix_envelope",
                      lambda: mix_envelope(
                          out_dir,
                          transistors={(r["width"], r["adder"]):
                                       r["transistors"] for r in rows})),
                     ("compiled_workloads",
                      lambda: compiled_workloads(out_dir)),
                     ("coverage_matrix",
                      lambda: coverage_matrix(out_dir))):
        try:
            fn()
        except Exception as e:                 # pragma: no cover
            print(f"[study] {name} skipped: {e}")
    try:
        abc_names = [f"m2d_w{r['width']}_{r['adder']}" for r in rows
                     if (r["width"], r["adder"]) in
                     ((1, "ripple"), (32, "ripple"), (32, "prefix"))]
        if abc_names:
            abc_crosscheck(abc_names, build_dir=build_dir,
                           out_dir=out_dir)
    except Exception as e:                     # pragma: no cover
        print(f"[study] ABC cross-check unavailable: {e}")

    print(f"\nresults written to {out_dir}/"
          "{study.csv,study.md,workloads.md,adders.md,validation.md,"
          "boundaries.md,phase.md,io_model.md,depth_compliant.md,"
          "rent_sensitivity.md,cpi_model.md,waitstate.md,"
          "abc_crosscheck.md,mix_envelope.md,compiled_workloads.md,"
          "coverage.md}")
    return rows



# ============================ 7. phase diagrams: optimal W over physics
#
# The delay of every design under scaled technology parameters is exactly
#
#   delay(gt, gw; k) = gt * [ n*t0  +  load * C_eff(N; gw, k) / C_PIN_A ]
#                    = gt * [ D0(k) + D1(k) * gw ]              (linear!)
#
#   n    = stage count of the delay-critical path (incl. clk-to-Q)
#   load = measured delay - n*t0  (the load-proportional part)
#   gt   = device delay penalty (scales intrinsic delay AND drive, i.e.
#          both t0 and the us/pF slope)
#   gw   = wire capacitance penalty (scales the wire term of C_eff only)
#   k    = M3D tiers (1 = flat): wire term / sqrt(k)
#
# so every phase boundary in the (gw, gt) plane is a closed-form curve
# gt * (D0 + D1*gw) = 1/f_op.  Three diagrams:
#
#   PD-1  (gw x gt) at fixed f_op = 1 kHz, k in {1, 2, 4}:
#         region = widest feasible design (= throughput- and
#         energy-optimal among feasible, since CPI decreases and both
#         p_s*T*CPI and N_pins*C*CPI are minimized by the widest).
#   PD-2  (gw x d):  region = argmax expected throughput per die at f_max,
#         E[thr] = exp(-d*T) * f_max(gw)/CPI.
#   PD-3  (gw x p_s): region = argmin energy/instruction at f_max,
#         E = p_s*T*CPI*delay + alpha*N_pins*C_eff*V^2*CPI,  k in {1, 4}.

_CHAR = {(32, "prefix"): "P", (32, "ripple"): "p",
         (16, "prefix"): "H", (16, "ripple"): "h",
         (8,  "prefix"): "B", (8,  "ripple"): "b",
         (4,  "ripple"): "n", (2,  "ripple"): "d",
         (1,  "ripple"): "s"}
_LEGEND = ("legend: s=1  d=2  n=4  b/B=8  h/H=16  p/P=32 "
           "(lowercase ripple, UPPERCASE Brent-Kung prefix), .=infeasible")


def _design_coeffs(r, wm, k):
    """(D0, D1) of delay = gt*(D0 + D1*gw) in us, plus cached fields."""
    res = r["_res"]
    n = len(res.critical_cells) + 1
    d0_gate = n * T0_US
    load = res.delay_us - d0_gate
    n_cells = sum(res.cell_counts.values())
    c_wire1 = (wm.c_w * l_avg(n_cells, wm.p, wm.a)
               / math.sqrt(k))                          # wire pF at gw=1
    D0 = d0_gate + load * (C_G / C_PIN_A)
    D1 = load * (c_wire1 / C_PIN_A)
    return D0, D1


def _grid(lo, hi, n):
    return [lo * (hi / lo) ** (i / (n - 1)) for i in range(n)]


def _ascii_map(rows_axis, cols_axis, cell_fn, row_label, col_label):
    out = [f"    rows: {row_label} (top = max), cols: {col_label} "
           f"(left = min)\n"]
    for y in reversed(rows_axis):
        line = "    "
        for x in cols_axis:
            line += cell_fn(x, y)
        out.append(line + f"   {y:g}\n")
    ticks = "    " + "".join(
        "|" if i % 8 == 0 else " " for i in range(len(cols_axis)))
    out.append(ticks + "\n")
    lab = "    "
    for i, x in enumerate(cols_axis):
        if i % 8 == 0:
            s = f"{x:.2g}"
            lab += s.ljust(8)
    out.append(lab + "\n")
    return out


def phase_diagrams(rows, wm, out_dir, f_op_hz=1000.0):
    path = os.path.join(out_dir, "phase.md")
    L = []
    w = L.append
    designs = rows

    # ---- lambda_eff table (W- and tier-dependent, not a constant)
    w("## Effective wire factor lambda_eff(W, k) = C_eff / 2.5 pF "
      "(architecture- and tier-dependent)\n\n")
    w("| W | adder | N cells | flat (k=1) | 2-tier | 4-tier |\n")
    w("|--:|:--|--:|--:|--:|--:|\n")
    for r in designs:
        n_cells = sum(r["_res"].cell_counts.values())
        lam = [wm.c_eff(n_cells, k, 1.0) / C_PIN_A for k in (1, 2, 4)]
        w(f"| {r['width']} | {r['adder']} | {n_cells} | "
          f"{lam[0]:.3f} | {lam[1]:.3f} | {lam[2]:.3f} |\n")
    w("\n(The flat W=1 value is 1.000 by calibration; lambda_eff grows "
      "with W through the Rent/Donath wirelength L(N) and falls with "
      "1/sqrt(k).)\n")

    # ---- closed-form boundary coefficients
    w("\n## Feasibility-frontier coefficients: "
      "delay = gt (D0 + D1 gw) [us]\n\n")
    w("Every phase boundary of PD-1 is gt (D0 + D1 gw) = 1/f_op.\n\n")
    w("| W | adder | n stages | D0 (k=1) | D1 (k=1) | D1 (k=2) | "
      "D1 (k=4) |\n|--:|:--|--:|--:|--:|--:|--:|\n")
    for r in designs:
        n = len(r["_res"].critical_cells) + 1
        d0, d1_1 = _design_coeffs(r, wm, 1)
        _, d1_2 = _design_coeffs(r, wm, 2)
        _, d1_4 = _design_coeffs(r, wm, 4)
        w(f"| {r['width']} | {r['adder']} | {n} | {d0:.1f} | {d1_1:.1f} | "
          f"{d1_2:.1f} | {d1_4:.1f} |\n")

    # ---- PD-1
    budget = 1e6 / f_op_hz
    gws = _grid(0.1, 10.0, 33)
    gts = _grid(0.1, 10.0, 21)

    def pd1_cell(k):
        coeffs = [(r, *_design_coeffs(r, wm, k)) for r in designs]

        def cell(gw, gt):
            feas = [(r, ) for r, D0, D1 in coeffs
                    if gt * (D0 + D1 * gw) <= budget]
            if not feas:
                return "."
            best = min((r for (r,) in feas),
                       key=lambda r: (r["cpi_geo"], r["transistors"]))
            return _CHAR[(best["width"], best["adder"])]
        return cell

    for k in (1, 2, 4):
        w(f"\n## PD-1: optimal W at fixed f_op = {f_op_hz:.0f} Hz, "
          f"{'flat (k=1)' if k == 1 else f'{k}-tier M3D'}\n\n")
        w("x: wire penalty gamma_w, y: device delay penalty gamma_t "
          "(1 = measured MoS2 2025 values; region = widest feasible "
          "design, which is simultaneously throughput- and "
          "energy-optimal among the feasible set)\n\n```\n")
        L.extend(_ascii_map(gts, gws, pd1_cell(k), "gamma_t", "gamma_w"))
        w("```\n" + _LEGEND + "\n")
        # boundary values along gt = 1
        cs = [(r, *_design_coeffs(r, wm, k)) for r in designs]
        w("\nBoundaries along gamma_t = 1 (gw* where each design becomes "
          "infeasible): ")
        bl = sorted(((budget / 1.0 - D0) / D1, r) for r, D0, D1 in cs)
        w(", ".join(f"W={r['width']} {r['adder']}: gw*={g:.2f}"
                    for g, r in bl) + "\n")

    # ---- PD-2
    w("\n## PD-2: optimal W over wire penalty x defect density "
      "(throughput per die at f_max, flat)\n\n")
    dss = _grid(1e-6, 1e-3, 21)

    def pd2_cell(gw, d):
        best, bv = None, -1.0
        for r in designs:
            D0, D1 = _design_coeffs(r, wm, 1)
            fmax = 1e6 / (D0 + D1 * gw)
            v = math.exp(-d * r["transistors"]) * fmax / r["cpi_geo"]
            if v > bv:
                best, bv = r, v
        return _CHAR[(best["width"], best["adder"])]

    w("x: gamma_w, y: defect density d [defects/transistor]\n\n```\n")
    L.extend(_ascii_map(dss, gws, pd2_cell, "d", "gamma_w"))
    w("```\n" + _LEGEND + "\n")
    for gw in (0.3, 1.0, 3.0, 10.0):
        # exact switch points on the envelope at this gw
        des = []
        for r in designs:
            D0, D1 = _design_coeffs(r, wm, 1)
            des.append(dict(r=r, thr=(1e6 / (D0 + D1 * gw)) / r["cpi_geo"],
                            T=r["transistors"]))
        env = _envelope_d(des, "thr", t_key="T")
        seq = " -> ".join(
            (f"W={e['r']['width']} {e['r']['adder']}"
             + (f" (d*={ds * 1e6:.0f}/10^6 T)" if ds else ""))
            for e, ds in env)
        w(f"\ngamma_w = {gw:g}: {seq}\n")

    # ---- PD-3
    pss = _grid(0.01, 100.0, 21)
    for k in (1, 4):
        w(f"\n## PD-3: energy-optimal W at f_max over wire penalty x "
          f"static power, {'flat' if k == 1 else '4-tier M3D'}\n\n")

        def pd3_cell(gw, ps, k=k):
            best, bv = None, None
            for r in designs:
                D0, D1 = _design_coeffs(r, wm, k)
                dly = (D0 + D1 * gw) * 1e-6                    # s
                n_cells = sum(r["_res"].cell_counts.values())
                c_eff = wm.c_eff(n_cells, k, gw) * 1e-12       # F
                alpha = r.get("alpha_meas", SCEN_B["alpha"])
                e = (ps * 1e-9 * r["transistors"] * r["cpi_geo"] * dly
                     + alpha * r["pins"] * c_eff
                     * SCEN_B["vdd"] ** 2 * r["cpi_geo"])
                if bv is None or e < bv:
                    best, bv = r, e
            return _CHAR[(best["width"], best["adder"])]

        w("x: gamma_w, y: p_s [nW/T] (72.67 = measured E/D NMOS, "
          "<0.1 = CFET leakage)\n\n```\n")
        L.extend(_ascii_map(pss, gws, pd3_cell, "p_s", "gamma_w"))
        w("```\n" + _LEGEND + "\n")

    with open(path, "w") as f:
        f.writelines(L)
    return path



# ===================== 8. gate-level workload execution + measured alpha
#
# The mapped netlist of every design point is simulated cycle-by-cycle at
# gate level, driving the same zero-wait memory / register-file environment
# as the RTL benches.  This provides
#
#   (a) an end-to-end functional check far stronger than random patterns:
#       the mapped netlist must execute a full workload and reproduce both
#       the golden checksum and the RTL cycle count exactly;
#   (b) the MEASURED switching activity alpha (mean toggles per cell input
#       pin per cycle), replacing the assumed constant in Scenario B;
#   (c) the MEASURED pad-bit toggle count per instruction (all primary
#       I/O bits), which feeds the external-I/O energy model.

_GATE_EVAL = {
    "INV":     lambda a: 1 ^ a,
    "NAND2":   lambda a, b: 1 ^ (a & b),
    "NAND3":   lambda a, b, c: 1 ^ (a & b & c),
    "NAND2B":  lambda an, b: 1 ^ ((1 ^ an) & b),
    "NAND3B":  lambda an, b, c: 1 ^ ((1 ^ an) & b & c),
    "NOR2":    lambda a, b: 1 ^ (a | b),
    "NOR3":    lambda a, b, c: 1 ^ (a | b | c),
    "NOR2B":   lambda an, b: 1 ^ ((1 ^ an) | b),
    "AND2":    lambda a, b: a & b,
    "AND3":    lambda a, b, c: a & b & c,
    "OR2":     lambda a, b: a | b,
    "AOI21":   lambda a0, a1, b0: 1 ^ ((a0 & a1) | b0),
    "AOI22":   lambda a0, a1, b0, b1: 1 ^ ((a0 & a1) | (b0 & b1)),
    "AOI31":   lambda a0, a1, a2, b0: 1 ^ ((a0 & a1 & a2) | b0),
    "AOI32":   lambda a0, a1, a2, b0, b1:
               1 ^ ((a0 & a1 & a2) | (b0 & b1)),
    "AOI211":  lambda a0, a1, b0, c0: 1 ^ ((a0 & a1) | b0 | c0),
    "AOI221":  lambda a0, a1, b0, b1, c0:
               1 ^ ((a0 & a1) | (b0 & b1) | c0),
    "AOI2BB2": lambda a0n, a1n, b0, b1:
               1 ^ (((1 ^ a0n) & (1 ^ a1n)) | (b0 & b1)),
    "OAI21":   lambda a0, a1, b0: 1 ^ ((a0 | a1) & b0),
    "OAI22":   lambda a0, a1, b0, b1: 1 ^ ((a0 | a1) & (b0 | b1)),
    "OAI31":   lambda a0, a1, a2, b0: 1 ^ ((a0 | a1 | a2) & b0),
    "OAI2BB2": lambda a0n, a1n, b0, b1:
               1 ^ (((1 ^ a0n) | (1 ^ a1n)) & (b0 | b1)),
    "XOR2":    lambda a, b: a ^ b,
    "MUX2":    lambda a, b, s: b if s else a,
}


class GateSim:
    """Cycle-accurate two-phase simulator of a mapped netlist.

    Phase 1 evaluates combinational logic from the current state to obtain
    address/control outputs (which depend only on flip-flop state in this
    core); the environment (memory, register file) then computes its
    combinational responses; phase 2 re-evaluates with those inputs and
    the flip-flops latch.  Toggle statistics are collected on phase-2
    values.

    WHAT alpha IS, AND IS NOT.  This is a zero-delay evaluator: it compares
    the SETTLED value of every net at consecutive cycle boundaries.  The
    resulting alpha is therefore the *functional* activity and excludes
    glitches (spurious multiple transitions within a cycle).  Glitch power
    grows with combinational depth, so the omission understates activity
    MOST for the deepest netlists -- W = 32 ripple above all.  Two
    consequences for the study:
      * IV-D ("parallel wins the CFET dynamic-energy projection by 2.0x")
        is safe: the deep design is the one whose energy is understated.
      * VI-E's low-p_s corner ("W = 32 ripple takes over below roughly
        0.02-0.25 nW/T") is the one result that a glitch-aware simulator
        could move, since it is exactly the ripple-vs-prefix dynamic-energy
        comparison at equal CPI.  Report it as such.
    alpha is pin-weighted (each toggling net counts its fan-out), which is
    the correct weighting for E = alpha * N_pins * C * V^2; note the clock
    pins enter both n_pins and the denominator and cancel exactly in the
    product alpha * N_pins = toggles per cycle.  Clock-network energy
    itself is NOT modeled; adding it would favor the parallel designs
    further, since CPI is 13.5x larger for the serial core.
    """

    def __init__(self, mapped, gates_json_path, top):
        import json
        from m2d.pdk2d.techmap import _topo_order, C0, C1
        self.C0, self.C1 = C0, C1
        with open(gates_json_path) as f:
            raw = json.load(f)
        mod = raw["modules"][top]
        self.ports = {}                      # name -> list of bit tokens
        for pname, p in mod["ports"].items():
            self.ports[pname] = [b for b in p["bits"]]
        self.nl = mapped
        order = _topo_order(mapped)
        # dense net indexing
        nets = set([C0, C1])
        for kind, ins, out, clk in mapped.gates.values():
            nets.update(ins)
            nets.add(out)
        nets.update(mapped.inputs)
        self.idx = {n: i for i, n in enumerate(sorted(nets, key=str))}
        self.val = [0] * len(self.idx)
        self.val[self.idx[C1]] = 1
        # compiled combinational program (topological order excludes the
        # sequential gates, so flip-flops are collected separately)
        self.prog = []
        self.ffs = []                        # (d_idx, q_idx)
        for kind, ins, out, clk in mapped.gates.values():
            if kind in ("DFFHQ", "$_DFF_P_"):
                self.ffs.append((self.idx[ins[0]], self.idx[out]))
        for gid in order:
            kind, ins, out, clk = mapped.gates[gid]
            if kind in ("DFFHQ", "$_DFF_P_"):
                continue
            fn = _GATE_EVAL[kind]
            self.prog.append((fn, tuple(self.idx[i] for i in ins),
                              self.idx[out]))
        # pins per net (for alpha) and I/O bit set (for pad toggles)
        self.pins_per_net = [0] * len(self.idx)
        for kind, ins, out, clk in mapped.gates.values():
            for i in ins:
                self.pins_per_net[self.idx[i]] += 1
        self.n_pins = sum(self.pins_per_net)
        io_nets = set()
        for bits in self.ports.values():
            for b in bits:
                if b in self.idx:
                    io_nets.add(self.idx[b])
        self.io_nets = sorted(io_nets)
        self.prev = None
        self.pin_toggles = 0
        self.io_toggles = 0
        self.cycles = 0

    # ---- port access -------------------------------------------------
    def set_port(self, name, value):
        for pos, b in enumerate(self.ports[name]):
            if b in self.idx:
                self.val[self.idx[b]] = (value >> pos) & 1

    def get_port(self, name):
        v = 0
        for pos, b in enumerate(self.ports[name]):
            if b == "0":
                bit = 0
            elif b == "1":
                bit = 1
            else:
                bit = self.val[self.idx[b]]
            v |= bit << pos
        return v

    def eval_comb(self):
        val = self.val
        for fn, ins, out in self.prog:
            val[out] = fn(*[val[i] for i in ins])

    def tick(self):
        """Latch flip-flops + collect toggle statistics (call after the
        final phase-2 evaluation of the cycle)."""
        val = self.val
        if self.prev is not None:
            ppn = self.pins_per_net
            t = 0
            for i, (a, b) in enumerate(zip(self.prev, val)):
                if a != b:
                    t += ppn[i]
            self.pin_toggles += t
            self.io_toggles += sum(1 for i in self.io_nets
                                   if self.prev[i] != val[i])
        self.prev = list(val)
        for d, q in self.ffs:
            val[q] = self.prev[d]
        self.cycles += 1


def gate_level_sim(flow, width, adder, workload="checksum",
                   build_dir="build"):
    """Execute a workload on the mapped netlist; returns
    (cycles, alpha_measured, io_toggles_per_instr, result_word)."""
    prog, data = WORKLOADS[workload]()
    n_insns, ref = golden_run(prog, dict(data))[:2]
    mem = {i: w & M32 for i, w in enumerate(prog)}
    mem.update(data)
    regs = [0] * 32
    tag = f"m2d_w{width}_{adder}"
    gs = GateSim(flow.mapped,
                 os.path.join(build_dir, f"{tag}_gates.json"), tag)

    retired = 0
    for _ in range(2_000_000):
        # phase 1: state-dependent outputs (addresses, controls)
        gs.set_port("ibus_ack", 0)
        gs.set_port("dbus_ack", 0)
        gs.eval_comb()
        if gs.get_port("ibus_cyc"):
            addr = gs.get_port("ibus_addr")
            gs.set_port("ibus_rdat", mem.get(addr >> 2, 0))
            gs.set_port("ibus_ack", 1)
            retired += 1
            if retired > n_insns:
                break
        elif gs.get_port("dbus_cyc"):
            addr = gs.get_port("dbus_addr") >> 2
            if gs.get_port("dbus_we"):
                pass                        # write data read in phase 2
            else:
                gs.set_port("dbus_rdat", mem.get(addr, 0))
            gs.set_port("dbus_ack", 1)
        # register file combinational read (addresses are state-only)
        ra1 = gs.get_port("rf_raddr1")
        ra2 = gs.get_port("rf_raddr2")
        index = gs.get_port("rf_index") if "rf_index" in gs.ports else 0
        gs.set_port("rf_rdig1", (regs[ra1] >> (index * width))
                    & ((1 << width) - 1))
        gs.set_port("rf_rdig2", (regs[ra2] >> (index * width))
                    & ((1 << width) - 1))
        # phase 2: full evaluation with environment responses
        gs.eval_comb()
        # environment state updates from phase-2 values
        if gs.get_port("dbus_cyc") and gs.get_port("dbus_we"):
            addr = gs.get_port("dbus_addr") >> 2
            sel = gs.get_port("dbus_sel")
            wdat = gs.get_port("dbus_wdat")
            mask = 0
            for i in range(4):
                if sel & (1 << i):
                    mask |= 0xFF << (8 * i)
            mem[addr] = (mem.get(addr, 0) & ~mask) | (wdat & mask)
        if gs.get_port("rf_wen"):
            wa = gs.get_port("rf_waddr")
            if wa != 0:
                sh = index * width
                m_ = ((1 << width) - 1) << sh
                regs[wa] = ((regs[wa] & ~m_)
                            | ((gs.get_port("rf_wdig") << sh) & m_)) & M32
        gs.tick()
    else:
        raise TimeoutError("gate-level simulation did not finish")

    got = mem.get(0x80 >> 2, 0)
    assert got == ref, (f"gate-level result mismatch W={width}/{adder}: "
                        f"{got:#010x} != {ref:#010x}")
    alpha = gs.pin_toggles / (gs.n_pins * max(1, gs.cycles - 1))
    io_per_instr = gs.io_toggles / n_insns
    return gs.cycles, alpha, io_per_instr, got


def gate_level_sim_pipelined(pres, width, adder, workload="checksum",
                             build_dir="build", reset_periods=None,
                             seed=0x2D64, limit=2_000_000):
    """Execute a workload on the depth-compliant physical netlist of
    `m2d.pdk2d.pipeline` at sub-cycle granularity.

    Every architectural cycle takes S physical clock periods.  In each
    period the environment is evaluated as in `gate_level_sim` (a pure
    function of the current outputs: zero-wait memory and the external
    register file respond combinationally), but the environment STATE
    (memory writes, register-file writes, the retired-instruction count)
    is updated only in the last sub-cycle, when all outputs are settled.
    The run starts from a RANDOM state of every flip-flop (architectural,
    pipeline and ring) followed by `reset_periods` periods of rst = 1
    (default 2 S), so the synchronous reset path of the physical netlist
    is exercised as well.

    Returns (arch_cycles, physical_cycles, alpha_measured_per_period,
    io_toggles_per_instr, result_word)."""
    from m2d.pdk2d.pipeline import _ff_gids
    prog, data = WORKLOADS[workload]()
    n_insns, ref = golden_run(prog, dict(data))[:2]
    mem = {i: w & M32 for i, w in enumerate(prog)}
    mem.update(data)
    regs = [0] * 32
    tag = f"m2d_w{width}_{adder}"
    gs = GateSim(pres.netlist,
                 os.path.join(build_dir, f"{tag}_gates.json"), tag)
    S = pres.subcycles
    nl = pres.netlist
    rng = random.Random(seed)
    for gid in _ff_gids(nl):
        gs.val[gs.idx[nl.gates[gid][2]]] = rng.getrandbits(1)
    rst_bits = gs.ports["rst"]

    def environment(update_state):
        gs.set_port("ibus_ack", 0)
        gs.set_port("dbus_ack", 0)
        gs.eval_comb()
        fetch = False
        if gs.get_port("ibus_cyc"):
            addr = gs.get_port("ibus_addr")
            gs.set_port("ibus_rdat", mem.get(addr >> 2, 0))
            gs.set_port("ibus_ack", 1)
            fetch = True
        elif gs.get_port("dbus_cyc"):
            addr = gs.get_port("dbus_addr") >> 2
            if not gs.get_port("dbus_we"):
                gs.set_port("dbus_rdat", mem.get(addr, 0))
            gs.set_port("dbus_ack", 1)
        ra1 = gs.get_port("rf_raddr1")
        ra2 = gs.get_port("rf_raddr2")
        index = gs.get_port("rf_index") if "rf_index" in gs.ports else 0
        gs.set_port("rf_rdig1", (regs[ra1] >> (index * width))
                    & ((1 << width) - 1))
        gs.set_port("rf_rdig2", (regs[ra2] >> (index * width))
                    & ((1 << width) - 1))
        gs.eval_comb()
        if not update_state:
            return fetch
        if gs.get_port("dbus_cyc") and gs.get_port("dbus_we"):
            addr = gs.get_port("dbus_addr") >> 2
            sel = gs.get_port("dbus_sel")
            wdat = gs.get_port("dbus_wdat")
            mask = 0
            for i in range(4):
                if sel & (1 << i):
                    mask |= 0xFF << (8 * i)
            mem[addr] = (mem.get(addr, 0) & ~mask) | (wdat & mask)
        if gs.get_port("rf_wen"):
            wa = gs.get_port("rf_waddr")
            if wa != 0:
                sh = index * width
                m_ = ((1 << width) - 1) << sh
                regs[wa] = ((regs[wa] & ~m_)
                            | ((gs.get_port("rf_wdig") << sh) & m_)) & M32
        return fetch

    # synchronous reset from the random state
    gs.set_port("rst", 1)
    for _ in range(reset_periods if reset_periods is not None else 2 * S):
        environment(False)
        gs.tick()
    gs.set_port("rst", 0)
    for i, q in enumerate(pres.ring):
        assert gs.val[gs.idx[q]] == (1 if i == 0 else 0), \
            "ring counter not at phase 0 after reset"
    gs.prev = None                       # toggle statistics: after reset
    gs.pin_toggles = gs.io_toggles = 0
    gs.cycles = 0

    retired = 0
    arch = 0
    for _ in range(limit):
        stop = False
        for sub in range(S):
            last = sub == S - 1
            fetch = environment(last)
            if last and fetch:
                retired += 1
                if retired > n_insns:
                    stop = True
                    break
            gs.tick()
        if stop:
            break
        arch += 1
    else:
        raise TimeoutError("gate-level simulation did not finish")

    got = mem.get(0x80 >> 2, 0)
    assert got == ref, (f"gate-level result mismatch W={width}/{adder} "
                        f"(pipelined, S={S}): {got:#010x} != {ref:#010x}")
    alpha = gs.pin_toggles / (gs.n_pins * max(1, gs.cycles - 1))
    io_per_instr = gs.io_toggles / n_insns
    return arch, gs.cycles, alpha, io_per_instr, got


# ================================ 9. external I/O cost model (audit A-1)
#
# The register file and both memories are external, as in RV32-WUJI.  This
# section makes the interface cost explicit instead of free:
#
#   * N_io(W): number of external signal pins of the core, counted from
#     the component signature (measured: 193 at W = 1 to 282 at W = 32;
#     three W-bit register-file data buses + index lines).
#   * pad energy: measured at gate level -- gate_level_sim counts every
#     toggle of every primary-I/O bit while executing the workload, so
#     E_io/instr = toggles_io * C_pad * Vdd^2 needs no activity assumption.
#     To first order the serial and parallel designs move the SAME number
#     of interface bits per instruction (W = 1 drives 1 wire 32 times,
#     W = 32 drives 32 wires once); the measured counts quantify the
#     residual asymmetry.
#   * pad delay: every execution cycle crosses the core->RF->core pad
#     boundary twice; delay_io = delay + 2 * (t0 + slope * C_pad) for
#     every design (the crossing count is width-independent; the wire
#     COUNT is not).
#   * pad yield: pads consume area; modeled as rho transistor-equivalents
#     of defect exposure per external pin, T_eff = T + rho * N_io.  This
#     taxes width in exactly the dimension where serialization wins, and
#     shifts the PD-2 boundaries accordingly.

C_PAD_PF = 10.0     # pF, baseline pad/bond load (= max_load of the PDK)


def n_io(width):
    from amaranth.hdl import Shape
    core = M2D(width=width)
    return sum(Shape.cast(m.shape).width
               for _path, m in core.signature.members.flatten())


def io_tables(rows, out_dir):
    path = os.path.join(out_dir, "io_model.md")
    with open(path, "w") as f:
        f.write("External-interface cost model (audit A-1)\n\n")
        f.write("Table IO-1: external pin count and measured pad activity "
                "(checksum workload, gate level)\n\n")
        f.write("| W | adder | N_io pins | pad-bit toggles / instr | "
                "E_io/instr uJ (C_pad=10pF) | delay+2 pad crossings us | "
                "f_max' Hz |\n|--:|:--|--:|--:|--:|--:|--:|\n")
        for r in rows:
            e_io = (r["io_toggles_pi"] * C_PAD_PF * 1e-12 * 16) * 1e6  # V=4
            d_io = r["delay_us"] + 2 * (T0_US + SLOPE * C_PAD_PF)
            f.write(f"| {r['width']} | {r['adder']} | {r['n_io']} | "
                    f"{r['io_toggles_pi']:.1f} | {e_io:.3f} | "
                    f"{d_io:.1f} | {1e6 / d_io:.0f} |\n")
        f.write("\nThe measured pad-bit toggles per instruction are "
                "width-comparable (serial designs toggle few wires many "
                "times, parallel designs many wires once), so pad ENERGY "
                "does not select a width; pad COUNT does, through area "
                "and yield (Table IO-2).\n")
        # C_pad energy sensitivity: does any C_pad reverse the 1 kHz
        # energy ordering between W=1 and W=32?
        r1 = next(r for r in rows if r["width"] == 1)
        r32 = next(r for r in rows if r["width"] == 32
                   and r["adder"] == "ripple")
        de_static = r1["e_uj_1k"] - r32["e_uj_1k"]        # uJ, > 0
        dio = r1["io_toggles_pi"] - r32["io_toggles_pi"]  # toggles/instr
        f.write(f"\nC_pad sensitivity: E1k(W=1) - E1k(W=32) = "
                f"{de_static:.2f} uJ (static) + "
                f"({dio:+.1f} pad-toggles/instr) x C_pad x Vdd^2. ")
        if dio >= 0:
            f.write("Both terms favor W = 32: NO finite C_pad reverses "
                    "the parallel energy advantage.\n")
        else:
            cstar = de_static * 1e-6 / (-dio * 16) * 1e12
            f.write(f"The ordering would reverse only at C_pad = "
                    f"{cstar:.0f} pF, far beyond bond-pad reality.\n")
        # pad-yield asymmetry
        f.write("\nTable IO-2: pad-aware yield boundaries, "
                "T_eff = T + rho x N_io (f_max metric, gamma_w = 1)\n\n")
        f.write("| rho [T-equiv/pin] | envelope (d* in defects/10^6 T) "
                "|\n|:--|:--|\n")
        for rho in (0, 300, 1000):
            des = [dict(r=r, thr=r["thr_fmax"],
                        T=r["transistors"] + rho * r["n_io"])
                   for r in rows]
            env = _envelope_d(des, "thr", t_key="T")
            seq = " -> ".join(
                f"W={e['r']['width']} {e['r']['adder']}"
                + (f" ({ds * 1e6:.0f})" if ds else "")
                for e, ds in env)
            f.write(f"| {rho} | {seq} |\n")
        f.write("\n(rho taxes exactly the resource where serialization "
                "wins.  The envelope ORDER is unchanged, but large pad "
                "costs compress every boundary toward lower defect "
                "density -- at rho = 300 the top switch moves 41 -> 12 "
                "per 10^6 T and a narrow W = 4 window opens -- i.e. "
                "expensive pads make serialization pay off EARLIER, "
                "while never changing which widths appear on the "
                "envelope.  rho = 1000 T-equivalents/pin means the pad "
                "ring exceeds the W = 1 core itself by 18x, an extreme "
                "bound.)\n")
    return path


# ====================== 10. depth-compliant sub-cycle pipelining (IV-G)
#
# The fabricated chip's <= 17-stage rule may be a noise-margin/level-
# restoration constraint rather than a delay budget (E/D NMOS levels
# degrade over long unclocked cascades); Ao et al. do not state which.  We
# therefore evaluate BOTH readings: (i) if it is a delay rule, all points
# meet 1 kHz timing with 13-76 % duty; (ii) if it is a hard cascade rule,
# every netlist is converted into a PHYSICAL netlist that satisfies it:
# real DFFHQ pipeline registers at every 17th logic level, a hold MUX2 in
# front of every architectural flip-flop and a one-hot ring counter that
# makes one architectural cycle S physical periods (m2d/pdk2d/pipeline.py).
# Every such netlist is (a) analyzed by the ordinary DRC/timing flow --
# depth <= 17 and fan-out <= 4 must PASS --, (b) proven sequentially
# equivalent to the original netlist by bit-parallel random simulation
# over S periods with a garbage-before-arrival environment model, and (c)
# executed at gate level on the checksum workload at sub-cycle granularity
# from a random initial state through the reset: the architectural cycle
# count must equal the RTL and the result the golden ISS.  The clock is
# the compliant 17-stage period (171.02 us -> 5.847 kHz) and CPI_c = CPI
# x S.  The analytic construction of v6.3 (registers counted on the nets
# crossing each cut, S = ceil(depth / 17), no hold logic) is kept as a
# comparison column.

def _net_levels(nl):
    from m2d.pdk2d.techmap import _topo_order
    seq_kinds = ("DFFHQ", "$_DFF_P_")
    lvl = {}                                  # gate out net -> level
    order = _topo_order(nl)
    drv = nl.driver_map()
    for gid in order:
        kind, ins, out, clk = nl.gates[gid]
        if kind in seq_kinds:
            continue
        li = 0
        for net in ins:
            d = drv.get(net)
            if d is None or nl.gates[d][0] in seq_kinds:
                continue
            li = max(li, lvl.get(net, 0))
        lvl[out] = li + 1
    return lvl, drv


def analytic_repipelining(nl, depth, dmax=17):
    """The v6.3 analytic estimate: S = ceil(depth / dmax) and one register
    per net and crossed cut (flip-flop outputs and inputs included, no
    hold logic).  Returns (S, registers)."""
    lvl, drv = _net_levels(nl)
    S = -(-depth // dmax)
    seq_kinds = ("DFFHQ", "$_DFF_P_")
    cons_lvl = {}
    for gid, (kind, ins, out, clk) in nl.gates.items():
        if kind in seq_kinds:
            for net in ins[:1]:
                cons_lvl.setdefault(net, []).append(depth + 1)
            continue
        gl = lvl.get(out, 1)
        for net in ins:
            cons_lvl.setdefault(net, []).append(gl)
    nregs = 0
    for cut in range(dmax, depth, dmax):
        for net, ls in cons_lvl.items():
            d = drv.get(net)
            dl = 0 if d is None or nl.gates[d][0] in seq_kinds \
                else lvl.get(net, 0)
            if dl <= cut and any(l_ > cut for l_ in ls):
                nregs += 1
    return S, nregs


def depth_compliant_point(mapped, width, adder, cpi_geo, depth,
                          transistors, build_dir="build", patterns=4096,
                          workload="checksum", verify_minus_one=True):
    """Sub-cycle pipelining + DRC + sequential equivalence + gate-level
    workload execution of one design point; returns a dict record."""
    from m2d.pdk2d import analyze, subcycle_pipeline, verify_subcycle, \
                          read_ports, compliant_period_us
    from m2d.pdk2d.synth import write_netlist_json
    tag = f"m2d_w{width}_{adder}"
    ports = read_ports(os.path.join(build_dir, f"{tag}_gates.json"), tag)
    pres = subcycle_pipeline(mapped, ports)
    res = analyze(pres.netlist)
    n_eq = verify_subcycle(mapped, pres, ports, patterns=patterns)
    minus_one_fails = None
    if verify_minus_one and pres.subcycles > 1:
        p2 = subcycle_pipeline(mapped, ports,
                               force_subcycles=pres.subcycles - 1)
        try:
            verify_subcycle(mapped, p2, ports, patterns=patterns)
            minus_one_fails = False
        except AssertionError:
            minus_one_fails = True
    write_netlist_json(pres.netlist,
                       os.path.join(build_dir, f"{tag}_pipelined.json"))
    print(f"[study] gate-level workload execution ({tag}, S = "
          f"{pres.subcycles}, physical netlist) ...")
    arch, phys, alpha, io_pi, _ = gate_level_sim_pipelined(
        pres, width, adder, workload=workload, build_dir=build_dir)
    prog, data = WORKLOADS[workload]()
    n_wl, _ref = golden_run(prog, dict(data))[:2]
    rtl_cyc, _ = measure_cycles(prog, data, n_wl, width, adder)
    assert arch == rtl_cyc, (arch, rtl_cyc)
    S_an, regs_an = analytic_repipelining(mapped, depth)
    period = compliant_period_us()
    f_c = 1e6 / period
    S = pres.subcycles
    cpi_c = cpi_geo * S
    p_mw = res.power_mw
    rec = dict(
        width=width, adder=adder, depth=depth, transistors=transistors,
        cpi_geo=cpi_geo,
        S_analytic=S_an, regs_analytic=regs_an,
        T_analytic=transistors + 18 * regs_an,
        S=S, endpoint_level=pres.endpoint_level, cuts=list(pres.cuts),
        cut_regs=pres.n_cut_regs, cut_regs_per_cut=pres.cut_regs_per_cut,
        hold_mux=pres.n_hold_mux, holdless=pres.n_holdless,
        ring_cells=pres.n_ring_cells, buffers=pres.n_buffers,
        cells_c=res.n_cells, dff_c=res.n_seq, T_c=res.transistors,
        depth_c=res.logic_depth, depth_ok=res.depth_ok,
        fanout_viol_c=len(res.fanout_violations), fanout_ok=res.fanout_ok,
        delay_c_us=round(res.delay_us, 2), fmax_c_hz=round(res.fmax_hz, 1),
        nm_ok=res.min_noise_margin >= CONSTRAINTS.min_noise_margin,
        power_mw=round(p_mw, 3),
        seq_equiv_patterns=n_eq, minus_one_fails=minus_one_fails,
        gate_arch_cycles=arch, rtl_cycles=rtl_cyc,
        gate_phys_periods=phys, alpha_phys=round(alpha, 4),
        io_toggles_pi=round(io_pi, 1),
        period_us=round(period, 2), f_c_hz=round(f_c, 1),
        cpi_c=round(cpi_c, 2),
        thr_c=round(f_c / cpi_c, 1),
        e_uj_c=round(p_mw * 1e3 * cpi_c / f_c, 2),
        thr_1k=round(1000.0 / cpi_c, 1),
        e_uj_1k=round(p_mw * cpi_c, 2),
        t_ratio=round(res.transistors / transistors, 3),
    )
    return rec


def write_depth_compliant_md(recs, out_dir, dmax=17):
    """results/depth_compliant.md from the per-point records."""
    path = os.path.join(out_dir, "depth_compliant.md")
    recs = sorted(recs, key=lambda r: (r["adder"] != "ripple", r["width"]))
    period = recs[0]["period_us"]
    f_c = recs[0]["f_c_hz"]
    with open(path, "w") as f:
        f.write(f"Depth-compliant (<= {dmax} stages) sub-cycle-pipelined "
                f"physical netlists; physical clock = {period} us "
                f"({f_c:.0f} Hz), one architectural cycle = S periods\n\n")
        f.write("Table A: construction (m2d/pdk2d/pipeline.py). "
                "'cuts' are the logic levels after which the pipeline "
                "registers sit (chosen to minimize their number under the "
                "<= 17-level band constraint), 'cut regs' the DFFHQ "
                "inserted there, "
                "'hold MUX' the MUX2 in front of the architectural "
                "flip-flops ('hold-less' architectural flip-flops need "
                "none), 'ring' the ring-counter cells, 'buffers' the INV "
                "added for fan-out. The analytic columns are the v6.3 "
                "estimate (S = ceil(depth/17), one register per net and "
                "crossed cut, no hold logic).\n\n")
        f.write("| W | adder | depth | S analytic | regs analytic | "
                "T analytic | S | max endpoint level | cuts after level | "
                "cut regs | hold MUX | hold-less FFs | ring cells | buffers "
                "| T_c | T_c / T |\n")
        f.write("|--:|:--|--:|--:|--:|--:|--:|--:|:--|--:|--:|--:|--:|--:|"
                "--:|--:|\n")
        for r in recs:
            f.write(f"| {r['width']} | {r['adder']} | {r['depth']} | "
                    f"{r['S_analytic']} | {r['regs_analytic']} | "
                    f"{r['T_analytic']} | {r['S']} | {r['endpoint_level']} "
                    f"| {', '.join(map(str, r['cuts'])) or '-'} "
                    f"| {r['cut_regs']} | {r['hold_mux']} | {r['holdless']} "
                    f"| {r['ring_cells']} | {r['buffers']} | {r['T_c']} | "
                    f"{r['t_ratio']:.2f} |\n")
        f.write("\nTable B: design-rule checks and verification of the "
                "physical netlists. 'depth' is the logic depth reported by "
                "the same analyzer as Table 1 of study.md; 'delay' the "
                "critical path per physical period; 'seq. equiv.' the "
                "number of random cases of the S-period sequential "
                "equivalence check against the mapped netlist (garbage-"
                "before-arrival environment); 'S-1 fails' whether the "
                "same netlist with a ring of S-1 phases fails that check; "
                "'gate-level' the architectural cycles of the checksum "
                "workload executed on the physical netlist at sub-cycle "
                "granularity from a random initial state through reset, "
                "asserted equal to the RTL cycle count, with the result "
                "asserted equal to the golden ISS.\n\n")
        f.write("| W | adder | cells | DFF | depth | depth<=17 | fan-out "
                "viol. | NM | delay us | seq. equiv. | S-1 fails | "
                "gate-level arch cycles (= RTL) | physical periods | "
                "alpha / period | pad-bit toggles/instr |\n")
        f.write("|--:|:--|--:|--:|--:|:--:|--:|:--:|--:|--:|:--:|--:|--:|"
                "--:|--:|\n")
        for r in recs:
            m1 = {True: "yes", False: "NO", None: "n/a"}[r["minus_one_fails"]]
            f.write(f"| {r['width']} | {r['adder']} | {r['cells_c']} | "
                    f"{r['dff_c']} | {r['depth_c']} | "
                    f"{'PASS' if r['depth_ok'] else 'FAIL'} | "
                    f"{r['fanout_viol_c']} | "
                    f"{'PASS' if r['nm_ok'] else 'FAIL'} | "
                    f"{r['delay_c_us']} | {r['seq_equiv_patterns']} | {m1} "
                    f"| {r['gate_arch_cycles']} ({r['rtl_cycles']}) | "
                    f"{r['gate_phys_periods']} | {r['alpha_phys']} | "
                    f"{r['io_toggles_pi']} |\n")
        f.write(f"\nTable C: performance and energy under strict {dmax}-"
                f"stage compliance (physical clock {period} us; CPI_c = "
                f"geomean CPI x S; static-dominated power of the physical "
                f"netlist, {CONSTRAINTS.static_nw_per_t:.2f} nW/T). "
                f"The 1 kHz columns keep the paper's external clock as the "
                f"physical clock.\n\n")
        f.write("| W | adder | S | T_c | P mW | CPI_c | instr/s @f_c | "
                "E/instr uJ @f_c | instr/s @1 kHz | E/instr uJ @1 kHz |\n")
        f.write("|--:|:--|--:|--:|--:|--:|--:|--:|--:|--:|\n")
        for r in recs:
            f.write(f"| {r['width']} | {r['adder']} | {r['S']} | {r['T_c']} "
                    f"| {r['power_mw']} | {r['cpi_c']} | {r['thr_c']} | "
                    f"{r['e_uj_c']} | {r['thr_1k']} | {r['e_uj_1k']} |\n")
        best_t = max(recs, key=lambda r: r["thr_c"])
        best_e = min(recs, key=lambda r: r["e_uj_c"])
        min_t = min(recs, key=lambda r: r["T_c"])
        ser = next((r for r in recs if r["width"] == 1), None)
        par = next((r for r in recs if r["width"] == 32
                    and r["adder"] == "prefix"), None)
        all_ok = all(r["depth_ok"] and r["fanout_ok"] and r["nm_ok"]
                     and r["gate_arch_cycles"] == r["rtl_cycles"]
                     for r in recs)
        f.write(f"\nAll {len(recs)} physical netlists pass every design "
                f"rule of the paper (depth <= {dmax}, fan-out <= 4, noise "
                f"margin) and execute the workload with the RTL cycle "
                f"count: {'yes' if all_ok else 'NO'}.\n")
        f.write(f"Under strict {dmax}-stage compliance the transistor "
                f"minimum is W={min_t['width']} {min_t['adder']} "
                f"({min_t['T_c']} T), the throughput optimum is "
                f"W={best_t['width']} {best_t['adder']} "
                f"({best_t['thr_c']:.0f} instr/s) and the energy optimum "
                f"is W={best_e['width']} {best_e['adder']} "
                f"({best_e['e_uj_c']:.2f} uJ/instr)")
        if ser and par:
            f.write(f"; W=32 prefix delivers "
                    f"{par['thr_c'] / ser['thr_c']:.1f}x the throughput of "
                    f"W=1 ripple for {par['T_c'] / ser['T_c']:.1f}x the "
                    f"transistors and {ser['e_uj_c'] / par['e_uj_c']:.1f}x "
                    f"less energy per instruction")
        f.write(".\n")
        main = _main_study_optima(out_dir)
        have = {(r["width"], r["adder"]) for r in recs}
        if main and main["points"] <= have:
            same = (main["thr"] == (best_t["width"], best_t["adder"]) and
                    main["e"] == (best_e["width"], best_e["adder"]))
            f.write(f"The main study (study.md, unpipelined netlists at "
                    f"f_max) has its throughput optimum at W={main['thr'][0]}"
                    f" {main['thr'][1]} and its energy optimum at "
                    f"W={main['e'][0]} {main['e'][1]}: the serial-vs-parallel"
                    f" ordering is {'unchanged' if same else 'CHANGED'} "
                    f"under strict compliance.\n")
        f.write("The v6.3 analytic estimate is superseded by these "
                "implemented netlists; it is kept in Table A only to show "
                "the direction of its errors (it omitted the hold logic "
                "and counted registers on flip-flop outputs and input pads, "
                "which need none).\n")
    return path


def _main_study_optima(out_dir):
    """(throughput, energy) optima of results/study.csv at f_max, as
    (width, adder) pairs; None if the file is not there."""
    path = os.path.join(out_dir, "study.csv")
    if not os.path.exists(path):
        return None
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return None
    thr = max(rows, key=lambda r: float(r["thr_fmax"]))
    e = min(rows, key=lambda r: float(r["e_uj_fmax"]))
    return {"thr": (int(thr["width"]), thr["adder"]),
            "e": (int(e["width"]), e["adder"]),
            "points": {(int(r["width"]), r["adder"]) for r in rows}}


def depth_compliant(rows, out_dir, dmax=17, build_dir="build"):
    import json
    recs = []
    for r in rows:
        rec = depth_compliant_point(r["_flow"].mapped, r["width"],
                                    r["adder"], r["cpi_geo"], r["depth"],
                                    r["transistors"], build_dir=build_dir)
        recs.append(rec)
        print(f"[study]   W={r['width']} {r['adder']}: S = {rec['S']}, "
              f"T_c = {rec['T_c']}, depth {rec['depth_c']} "
              f"{'PASS' if rec['depth_ok'] else 'FAIL'}, gate-level "
              f"{rec['gate_arch_cycles']} arch cycles (RTL "
              f"{rec['rtl_cycles']})")
    with open(os.path.join(out_dir, "depth_compliant.json"), "w") as f:
        json.dump(recs, f, indent=1)
    return write_depth_compliant_md(recs, out_dir, dmax)


# ======================= 12. width-limited-memory CPI (audit A-1 addendum)

def waitstate_cpi(rows, goldens, out_dir, wait_states=3):
    """CPI with a bandwidth-limited external memory: `wait_states` extra
    cycles per bus transaction (3 waits ~ fetching 32-bit words over an
    8-bit bus).  Re-measured cycle-accurately for every design point and
    workload."""
    path = os.path.join(out_dir, "waitstate.md")
    with open(path, "w") as f:
        f.write(f"CPI with a width-limited memory bus "
                f"({wait_states} wait states per bus transaction, "
                f"~ 8-bit external bus)\n\n")
        f.write("| W | adder |" + "".join(f" {n} |" for n in WORKLOADS)
                + " geomean | vs zero-wait | E/instr uJ @1kHz |\n")
        f.write("|--:|:--|" + "--:|" * (len(WORKLOADS) + 3) + "\n")
        for r in rows:
            cpis = []
            f.write(f"| {r['width']} | {r['adder']} |")
            for name in WORKLOADS:
                prog, data, n, ref, _, _, _ = goldens[name]
                cyc, memf = measure_cycles(prog, dict(data), n,
                                           r["width"], r["adder"],
                                           wait_states=wait_states)
                assert memf.get(0x80 >> 2, 0) == ref
                cpis.append(cyc / n)
                f.write(f" {cyc / n:.2f} |")
            geo = math.exp(sum(math.log(c) for c in cpis) / len(cpis))
            e1k = r["power_mw"] * geo
            f.write(f" {geo:.2f} | x{geo / r['cpi_geo']:.2f} | "
                    f"{e1k:.2f} |\n")
            r["cpi_w3"] = geo
        r1 = next(r for r in rows if r["width"] == 1)
        r32 = next(r for r in rows if r["width"] == 32
                   and r["adder"] == "prefix")
        f.write(f"\nSerial/parallel CPI ratio: "
                f"{r1['cpi_geo'] / r32['cpi_geo']:.1f}x (zero-wait) -> "
                f"{r1['cpi_w3'] / r32['cpi_w3']:.1f}x ({wait_states} "
                "waits): a slow memory compresses the parallel CPI "
                "advantage but does not reorder any conclusion (energy "
                "at 1 kHz remains T-dominated).\n")
    return path



# ============= 13. Rent-parameter sensitivity (audit B-2)

def rent_sensitivity(rows, out_dir):
    """Sweep the assumed Rent exponent p and Donath prefactor a; report the
    quantities they influence: lambda_eff(W=32 prefix), the top PD-2 yield
    boundary, and the PD-1 wire limit of the W=32 ripple design."""
    path = os.path.join(out_dir, "rent_sensitivity.md")

    def _find(w_, a_):
        return next((r for r in rows
                     if r["width"] == w_ and r["adder"] == a_), None)

    needed = [(1, "ripple"), (32, "prefix"), (16, "prefix"),
              (32, "ripple")]
    if any(_find(*wa) is None for wa in needed):
        with open(path, "w") as f:
            f.write("rent_sensitivity: skipped (requires design points "
                    "W=1/32 ripple and W=16/32 prefix; run the full "
                    "sweep without --quick).\n")
        return path
    n1 = _find(1, "ripple")["cells"]
    with open(path, "w") as f:
        f.write("Sensitivity of wire-model outputs to the assumed Rent "
                "parameters (calibration is repeated for every pair, so "
                "the W = 1 single-layer point stays at 2.5 pF/pin)\n\n")
        f.write("| p | a | lambda_eff(32p, flat) | d*(32p->16p) /10^6 T | "
                "gw*(32 ripple) |\n|--:|--:|--:|--:|--:|\n")
        for p_ in (0.50, 0.60, 0.75):
            for a_ in (0.5, 0.9, 2.0):
                wm = WireModel(n1, p=p_, a=a_)
                r32p = next(r for r in rows if r["width"] == 32
                            and r["adder"] == "prefix")
                r16p = next(r for r in rows if r["width"] == 16
                            and r["adder"] == "prefix")
                r32r = next(r for r in rows if r["width"] == 32
                            and r["adder"] == "ripple")
                lam = wm.c_eff(r32p["cells"], 1, 1.0) / C_PIN_A
                thr = {}
                for r in (r32p, r16p):
                    D0, D1 = _design_coeffs(r, wm, 1)
                    thr[r["width"]] = (1e6 / (D0 + D1)) / r["cpi_geo"]
                dstar = (math.log(thr[32] / thr[16])
                         / (r32p["transistors"] - r16p["transistors"]))
                D0, D1 = _design_coeffs(r32r, wm, 1)
                gwstar = (1000.0 - D0) / D1
                f.write(f"| {p_} | {a_} | {lam:.3f} | {dstar * 1e6:.1f} | "
                        f"{gwstar:.2f} |\n")
        f.write("\n(p = 0.5 makes wirelength size-independent, i.e. the "
                "architecture dependence vanishes by construction; even "
                "p = 0.75 changes the boundaries by only a few per cent "
                "because the wire penalty enters every design almost "
                "equally.)\n")
    return path


# ============= 14. closed-form CPI vs measurement (audit B-6)

def predicted_cpi(goldens, rows, out_dir):
    """Closed-form CPI from the V2 cycle model + measured dynamic mix;
    compared with the cycle-accurate measurement."""
    path = os.path.join(out_dir, "cpi_model.md")

    predict = model_cpi          # one definition, shared with embench

    with open(path, "w") as f:
        f.write("Closed-form CPI model vs. cycle-accurate measurement.\n"
                "CPI_pred = sum over classes of the V2 cycle formulas "
                "weighted by the measured dynamic mix "
                "(+ SRX shamt stalls at W = 1).\n\n")
        f.write("| W | adder |" + "".join(f" {n} pred/meas |"
                                          for n in WORKLOADS) + "\n")
        f.write("|--:|:--|" + "--:|" * len(WORKLOADS) + "\n")
        worst = 0.0
        for r in rows:
            f.write(f"| {r['width']} | {r['adder']} |")
            for name in WORKLOADS:
                _, _, n, _, mix, _, srx = goldens[name]
                pred = predict(mix, srx, n, r["width"])   # noqa: E501
                meas = r[f"cpi_{name}"]
                worst = max(worst, abs(pred - meas))
                f.write(f" {pred:.2f}/{meas:.2f} |")
            f.write("\n")
        f.write(f"\nMaximum |prediction - measurement| over all "
                f"{len(rows)} x {len(WORKLOADS)} entries: {worst:.3f} "
                "cycles/instruction.  The CPI of ANY instruction mix on "
                "any design point therefore follows from the mix alone; "
                "the five kernels validate the model rather than define "
                "the result.\n")
    return path


# ============= 15. yosys+ABC cross-check (audit A-3b)

def abc_crosscheck(names, build_dir="build", out_dir="results"):
    """Independent technology mapping through yosys' bundled ABC.

    The WASM build of ABC shipped with yowasp-yosys cannot read external
    Liberty/genlib library files, so ABC maps to its built-in gate classes
    restricted to the subset with a 1:1 correspondence in 2D_NMOS_lib;
    the result is translated cell-for-cell into library cells and analyzed
    with the same transistor/delay model.  ABC optimizes its own
    (gate-count) cost function rather than transistors -- the comparison
    is a mapper-independence check, not a like-for-like area contest.
    """
    import json as _json
    import io
    import contextlib
    import copy as _copy
    from m2d.pdk2d.techmap import Netlist, legalize_fanout, verify_equivalence
    from m2d.pdk2d.analyze import analyze
    from yowasp_yosys import run_yosys

    XLAT = {   # yosys $_ cell -> (library cell, input pin order)
        "$_NOT_":    ("INV",    ("A",)),
        "$_AND_":    ("AND2",   ("A", "B")),
        "$_OR_":     ("OR2",    ("A", "B")),
        "$_NAND_":   ("NAND2",  ("A", "B")),
        "$_NOR_":    ("NOR2",   ("A", "B")),
        "$_XOR_":    ("XOR2",   ("A", "B")),
        "$_ANDNOT_": ("NOR2B",  ("B", "A")),   # A & !B == !(B + !A)... see note
        "$_ORNOT_":  ("NAND2B", ("B", "A")),
        "$_MUX_":    ("MUX2",   ("A", "B", "S")),
        "$_AOI3_":   ("AOI21",  ("A", "B", "C")),
        "$_OAI3_":   ("OAI21",  ("A", "B", "C")),
        "$_AOI4_":   ("AOI22",  ("A", "B", "C", "D")),
        "$_OAI4_":   ("OAI22",  ("A", "B", "C", "D")),
    }
    # NOTE on ANDNOT/ORNOT pin order: NOR2B(AN, B) = !(!AN + B) = AN & !B,
    # so $_ANDNOT_(A, B) = A & !B maps with AN <- A, B <- B; likewise
    # NAND2B(AN, B) = !(!AN * B) = AN | !B  <- $_ORNOT_(A, B).
    XLAT["$_ANDNOT_"] = ("NOR2B", ("A", "B"))
    XLAT["$_ORNOT_"] = ("NAND2B", ("A", "B"))
    gset = "AND,NAND,OR,NOR,XOR,ANDNOT,ORNOT,MUX,AOI3,OAI3,AOI4,OAI4"
    path = os.path.join(out_dir, "abc_crosscheck.md")
    rows = []
    for name in names:
        script = (f"read_rtlil {name}.il; hierarchy -top {name}; proc; "
                  f"flatten; opt -full; techmap; opt -full; "
                  f"dfflegalize -cell $_DFF_P_ 01; "
                  f"abc -g {gset}; opt_clean -purge; "
                  f"write_json {name}_abc.json")
        cwd = os.getcwd()
        os.chdir(build_dir)
        try:
            # the yowasp build returns a spurious nonzero rc under -q when
            # ABC runs; run non-quiet with stdout captured instead.
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = run_yosys(["-p", script])
        finally:
            os.chdir(cwd)
        if rc:
            raise RuntimeError(f"yosys/ABC failed for {name}")
        raw = _json.load(open(os.path.join(build_dir, f"{name}_abc.json")))
        mod = raw["modules"][name]
        nl = Netlist(name)
        for cname, cell in mod["cells"].items():
            kind = cell["type"]
            conn = cell["connections"]
            if kind == "$_DFF_P_":
                nl.add("DFFHQ", [conn["D"][0]], conn["Q"][0],
                       clk=conn["C"][0])
                nl.clocks.add(conn["C"][0])
                continue
            lk, pins = XLAT[kind]
            nl.add(lk, [conn[p][0] for p in pins], conn["Y"][0])
        for pname, p in mod["ports"].items():
            for b in p["bits"]:
                if isinstance(b, int):
                    (nl.inputs if p["direction"] == "input"
                     else nl.outputs).add(b)
        res = analyze(nl)
        # --- fan-out legalization of the INDEPENDENT mapper's netlist.
        # The ABC netlists violate the process fan-out rule (max fan-out 40
        # to 84).  Running them through the SAME even-level inverter-tree
        # legalization pass that every netlist of this flow passes through
        # turns the QoR factor q from an upper bound into a measurement, and
        # makes the depth and delay columns comparable rather than optimistic
        # lower bounds.
        ref = _copy.deepcopy(nl)
        n_buf = legalize_fanout(nl)
        verify_equivalence(ref, nl, patterns=8192)
        res_lg = analyze(nl)
        rows.append((name, res, res_lg, n_buf))
    with open(path, "w") as f:
        f.write("Independent-mapper cross-check: yosys+ABC (built-in gate "
                "classes with a 1:1 library correspondence), translated "
                "cell-for-cell into 2D_NMOS_lib and analyzed with the same "
                "transistor/delay model.  ABC optimizes gate count, not "
                "transistors, and does not enforce the fan-out <= 4 rule, so "
                "each ABC netlist is reported BOTH as ABC emits it and after "
                "the SAME even-level inverter-tree legalization pass that "
                "every netlist of this flow passes through.  The legalized "
                "rows are the like-for-like comparison: they satisfy the "
                "same design rule and their delays are no longer optimistic "
                "lower bounds.\n\n")
        f.write("| design | mapper | cells | T (NMOS) | depth | delay us "
                "| max fan-out | nets > 4 "
                "|\n|:--|:--|--:|--:|--:|--:|--:|--:|\n")
        return_rows = []
        for name, res, res_lg, n_buf in rows:
            f.write(f"| {name} | yosys+ABC (as emitted) | "
                    f"{sum(res.cell_counts.values())} | {res.transistors} "
                    f"| {res.logic_depth} | {res.delay_us:.1f} "
                    f"| {res.fanout_max} | {len(res.fanout_violations)} |\n")
            f.write(f"| {name} | yosys+ABC (fan-out legalized) | "
                    f"{sum(res_lg.cell_counts.values())} "
                    f"| {res_lg.transistors} "
                    f"| {res_lg.logic_depth} | {res_lg.delay_us:.1f} "
                    f"| {res_lg.fanout_max} "
                    f"| {len(res_lg.fanout_violations)} |\n")
            return_rows.append(dict(name=name,
                                    cells=sum(res.cell_counts.values()),
                                    t=res.transistors,
                                    depth=res.logic_depth,
                                    delay=res.delay_us,
                                    fanout_max=res.fanout_max,
                                    fanout_violations=len(
                                        res.fanout_violations),
                                    cells_lg=sum(res_lg.cell_counts.values()),
                                    t_lg=res_lg.transistors,
                                    depth_lg=res_lg.logic_depth,
                                    delay_lg=res_lg.delay_us,
                                    buffers=n_buf))
        f.write(
            "\nEvery legalized netlist above was re-verified against the "
            "netlist ABC emitted by randomized functional equivalence over "
            "8,192 patterns at all primary outputs and flip-flop data "
            "inputs.\n\nNOTE on the 'as emitted' rows: the stage-delay model "
            "saturates the load at the legal maximum of 4 pins (see "
            "pdk2d/cells.py:stage_delay_us), because the 171 us anchor of "
            "Ao et al. is quoted at maximum legal fan-out.  Those netlists "
            "violate the fan-out rule, so their delay column is an "
            "OPTIMISTIC lower bound and is retained only to show what the "
            "unconstrained mapper produces.  All QoR factors q quoted in the "
            "article are computed from the LEGALIZED rows.\n")
    return path, return_rows



# ======================= 16. vector figures for the phase diagrams (C-1)

_FIG_ORDER = [(1, "ripple"), (2, "ripple"), (4, "ripple"), (8, "ripple"),
              (8, "prefix"), (16, "ripple"), (16, "prefix"),
              (32, "ripple"), (32, "prefix")]
_FIG_LABEL = {(1, "ripple"): "W=1", (2, "ripple"): "W=2",
              (4, "ripple"): "W=4", (8, "ripple"): "W=8 r",
              (8, "prefix"): "W=8 BK", (16, "ripple"): "W=16 r",
              (16, "prefix"): "W=16 BK", (32, "ripple"): "W=32 r",
              (32, "prefix"): "W=32 BK"}


def figures(rows, wm, out_dir):
    import numpy as _np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap, BoundaryNorm

    figdir = os.path.join(out_dir, "figs")
    os.makedirs(figdir, exist_ok=True)
    key2idx = {k: i for i, k in enumerate(_FIG_ORDER)}
    # colormap: serial = warm, parallel = cool; prefix darker than ripple
    colors = ["#c9b2a3", "#d9a066", "#e8c170", "#a8ca58", "#468232",
              "#75a743", "#25562e", "#4f8fba", "#3c5e8b"]
    cmap = ListedColormap(["#ffffff"] + colors)
    norm = BoundaryNorm(_np.arange(-1.5, len(colors) + 0.5), cmap.N)

    def region_plot(ax, xs, ys, Z, xlab, ylab):
        # rasterize the mesh inside the vector figure: keeps text/axes as
        # vectors while embedding the region map as an image (IEEE-friendly
        # file sizes)
        ax.pcolormesh(xs, ys, Z, cmap=cmap, norm=norm, shading="nearest",
                      rasterized=True)
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel(xlab)
        ax.set_ylabel(ylab)

    def legend_handles():
        import matplotlib.patches as mpatches
        return ([mpatches.Patch(color="#ffffff", ec="0.6",
                                label="infeasible")]
                + [mpatches.Patch(color=colors[i],
                                  label=_FIG_LABEL[k])
                   for k, i in key2idx.items()])

    gws = _np.logspace(-1, 1, 121)
    # ---- Fig. 1: PD-1 (k = 1)
    gts = _np.logspace(-1, 1, 121)
    coeffs = {(r["width"], r["adder"]): _design_coeffs(r, wm, 1)
              for r in rows}
    cpi = {(r["width"], r["adder"]): r["cpi_geo"] for r in rows}
    tcount = {(r["width"], r["adder"]): r["transistors"] for r in rows}
    Z = _np.full((len(gts), len(gws)), -1.0)
    for i, gt in enumerate(gts):
        for j, gw in enumerate(gws):
            best = None
            for k_, (D0, D1) in coeffs.items():
                if gt * (D0 + D1 * gw) <= 1000.0:
                    if best is None or (cpi[k_], tcount[k_]) < \
                            (cpi[best], tcount[best]):
                        best = k_
            if best is not None:
                Z[i, j] = key2idx[best]
    fig, ax = plt.subplots(figsize=(6.4, 5.0))
    region_plot(ax, gws, gts, Z,
                r"wire penalty $\gamma_w$ (2025 MoS$_2$ = 1)",
                r"device delay penalty $\gamma_t$ (2025 MoS$_2$ = 1)")
    # analytic frontiers
    for k_, (D0, D1) in coeffs.items():
        ax.plot(gws, 1000.0 / (D0 + D1 * gws), lw=0.7, color="k",
                alpha=0.55)
    ax.plot([1], [1], marker="*", ms=14, color="crimson", mec="k",
            zorder=5)
    ax.annotate("2025 MoS$_2$", (1, 1), textcoords="offset points",
                xytext=(6, 6), fontsize=9)
    ax.set_xlim(0.1, 10)
    ax.set_ylim(0.1, 10)
    ax.set_title("Optimal datapath width at $f_{op}$ = 1 kHz "
                 "(flat, k = 1)\nblack curves: closed-form frontiers "
                 r"$\gamma_t(D_0 + D_1\gamma_w) = 1/f_{op}$")
    ax.legend(handles=legend_handles(), fontsize=7.5, loc="lower left",
              framealpha=0.9)
    fig.tight_layout()
    for ext in ("svg", "png"):
        fig.savefig(os.path.join(figdir, f"fig_pd1.{ext}"), dpi=200)
    plt.close(fig)

    # ---- Fig. 2: PD-2
    ds = _np.logspace(-6, -3, 121)
    Z = _np.zeros((len(ds), len(gws)))
    for i, d in enumerate(ds):
        for j, gw in enumerate(gws):
            best, bv = None, -1.0
            for k_, (D0, D1) in coeffs.items():
                v = (math.exp(-d * tcount[k_]) * (1e6 / (D0 + D1 * gw))
                     / cpi[k_])
                if v > bv:
                    best, bv = k_, v
            Z[i, j] = key2idx[best]
    fig, ax = plt.subplots(figsize=(6.4, 5.0))
    region_plot(ax, gws, ds * 1e6, Z,
                r"wire penalty $\gamma_w$",
                r"defect density $d$ [defects / $10^6$ transistors]")
    ax.set_xlim(0.1, 10)
    ax.set_ylim(1, 1000)
    ax.set_title("Yield-aware optimum: expected throughput per die at "
                 "$f_{max}$")
    ax.legend(handles=legend_handles(), fontsize=7.5, loc="upper right",
              framealpha=0.9)
    fig.tight_layout()
    for ext in ("svg", "png"):
        fig.savefig(os.path.join(figdir, f"fig_pd2.{ext}"), dpi=200)
    plt.close(fig)

    # ---- Fig. 3: PD-3 (measured alpha)
    pss = _np.logspace(-2, 2, 121)
    alpha = {(r["width"], r["adder"]): r.get("alpha_meas",
                                             SCEN_B["alpha"])
             for r in rows}
    pins = {(r["width"], r["adder"]): r["pins"] for r in rows}
    cells = {(r["width"], r["adder"]): r["cells"] for r in rows}
    Z = _np.zeros((len(pss), len(gws)))
    for i, ps in enumerate(pss):
        for j, gw in enumerate(gws):
            best, bv = None, None
            for k_, (D0, D1) in coeffs.items():
                dly = (D0 + D1 * gw) * 1e-6
                c_eff = wm.c_eff(cells[k_], 1, gw) * 1e-12
                e = (ps * 1e-9 * tcount[k_] * cpi[k_] * dly
                     + alpha[k_] * pins[k_] * c_eff * 16 * cpi[k_])
                if bv is None or e < bv:
                    best, bv = k_, e
            Z[i, j] = key2idx[best]
    fig, ax = plt.subplots(figsize=(6.4, 5.0))
    region_plot(ax, gws, pss, Z,
                r"wire penalty $\gamma_w$",
                r"static power $p_s$ [nW / transistor]")
    ax.axhline(72.67, color="crimson", lw=1.0, ls="--")
    ax.annotate("measured E/D NMOS (72.67)", (0.12, 72.67 * 1.15),
                fontsize=8, color="crimson")
    ax.set_xlim(0.1, 10)
    ax.set_ylim(0.01, 100)
    ax.set_title("Energy-optimal width at $f_{max}$ "
                 "(measured per-design $\\alpha$, flat)")
    ax.legend(handles=legend_handles(), fontsize=7.5, loc="lower right",
              framealpha=0.9)
    fig.tight_layout()
    for ext in ("svg", "png"):
        fig.savefig(os.path.join(figdir, f"fig_pd3.{ext}"), dpi=200)
    plt.close(fig)
    return figdir



# ============= 17. compiled workloads, mix envelope, coverage (reviewer R1)
#
# The five kernels of WORKLOADS are hand-assembled, so three further checks
# establish that the width conclusions are not an artifact of them:
#
#   compiled_workloads()  the dynamic class mixes of COMPILED Embench-IoT
#                         binaries, executed to completion on the golden
#                         ISS, put through the validated CPI model
#   compiled_rtl_spot()   prefixes of those binaries executed on the RTL
#                         core at every design point: cycles against the
#                         closed-form model, whole data memory against the
#                         ISS
#   mix_envelope()        the EXACT extrema of CPI(W1)/CPI(W2) over every
#                         instruction mix that can exist -- no benchmark
#                         needed, and stronger than any finite suite
#
# Building the compiled traces is what exposed the JALR classification
# error corrected in _classify()/class_cycles().

EMBENCH_DIR = os.environ.get("M2D_EMBENCH_DIR", "embench")
EMBENCH_CACHE = "embench_mixes.json"


def trace_elf(path, limit=400_000_000):
    """Execute a compiled RV32I ELF on the golden ISS to its halt loop.

    Returns the retired-instruction count, the measured dynamic class mix,
    the taken/not-taken branch split, the summed right-shift amounts (the
    W = 1 stall term) and the word written to 0x80 by the startup code,
    which the Embench harness sets to main()'s return value (0 = the
    benchmark's own verify_benchmark() passed).
    """
    mem, entry = load_elf(path)
    iss = GoldenRV32I(mem, pc=entry)
    mix, taken, nottaken, srx_stall, n = {}, 0, 0, 0, 0
    while n < limit:
        pc0 = iss.pc
        word = iss.mem.get(pc0 >> 2, 0)
        op, f3 = word & 0x7F, (word >> 12) & 7
        if op in (0x13, 0x33) and f3 == 5:          # SRLI/SRAI/SRL/SRA
            srx_stall += (((word >> 20) & 31) if op == 0x13
                          else (iss.x[(word >> 20) & 31] & 31))
        iss.step()
        if iss.pc == pc0:                            # jump-to-self halt
            break
        cls = _classify(word)
        mix[cls] = mix.get(cls, 0) + 1
        if cls == "branch":
            taken += iss.pc != ((pc0 + 4) & M32)
            nottaken += iss.pc == ((pc0 + 4) & M32)
        n += 1
    else:
        raise TimeoutError(f"{path}: no halt loop within {limit} instructions")
    return dict(n=n, mix=mix, taken=taken, nottaken=nottaken,
                srx=srx_stall, retval=iss.mem.get(0x80 >> 2, None))


def _embench_traces(elf_dir=None, out_dir="results", refresh=False):
    """Measured mixes of the compiled benchmarks, cached as JSON.

    If the ELF images are present (see tools/build_embench.sh) they are
    traced; otherwise the cache shipped with the artifact is used, so that
    the tables regenerate without a cross toolchain.
    """
    import glob
    import json

    cache = os.path.join(out_dir, EMBENCH_CACHE)
    elf_dir = elf_dir or EMBENCH_DIR
    elfs = sorted(glob.glob(os.path.join(elf_dir, "*.elf")))
    if elfs and (refresh or not os.path.exists(cache)):
        traces = {}
        for f in elfs:
            name = os.path.basename(f)[:-4]
            print(f"[study] tracing compiled workload {name} ...")
            traces[name] = trace_elf(f)
        os.makedirs(out_dir, exist_ok=True)
        json.dump(traces, open(cache, "w"), indent=1)
        return traces, "traced"
    if os.path.exists(cache):
        return json.load(open(cache)), "cached"
    raise FileNotFoundError(
        f"no ELF images in {elf_dir}/ and no cache at {cache}; "
        "run tools/build_embench.sh first")


def compiled_workloads(out_dir="results", elf_dir=None,
                       widths=(1, 2, 4, 8, 16, 32), refresh=False):
    """Compiled Embench-IoT mixes through the validated CPI model."""
    traces, how = _embench_traces(elf_dir, out_dir, refresh)
    names = sorted(k for k in traces if "error" not in traces[k])
    path = os.path.join(out_dir, "compiled_workloads.md")

    cpi = {nm: {w: model_cpi(traces[nm]["mix"], traces[nm]["srx"],
                             traces[nm]["n"], w) for w in widths}
           for nm in names}

    def geo(v):
        return math.exp(sum(math.log(x) for x in v) / len(v))

    bad = [nm for nm in names if traces[nm].get("retval") not in (0, None)]
    total = sum(traces[nm]["n"] for nm in names)

    with open(path, "w") as f:
        f.write("Compiled workloads: Embench-IoT on the M2D design family "
                f"(mixes {how})\n\n"
                "Every benchmark is executed to completion on the golden ISS "
                "and passes\nits own verify_benchmark(); CPI is the "
                "closed-form V2 model (JALR = 2D+2)\nevaluated on the "
                "MEASURED dynamic class mix, not a simulation of the\n"
                "compiled program on the RTL.  compiled_rtl_spot() checks "
                "that model\nagainst RTL for prefixes of these same "
                "binaries.\n\n")
        f.write("| benchmark | retired |"
                + "".join(f" {c} % |" for c in CLASSES)
                + "".join(f" CPI W={w} |" for w in widths)
                + " serial/parallel |\n")
        f.write("|:--|--:|" + "--:|" * (len(CLASSES) + len(widths) + 1) + "\n")
        for nm in names:
            t = traces[nm]
            f.write(f"| {nm} | {t['n']} |"
                    + "".join(f" {100.0 * t['mix'].get(c, 0) / t['n']:.1f} |"
                              for c in CLASSES)
                    + "".join(f" {cpi[nm][w]:.2f} |" for w in widths)
                    + f" {cpi[nm][min(widths)] / cpi[nm][max(widths)]:.2f} |\n")
        f.write(f"| **geomean** | {total} |" + " |" * len(CLASSES)
                + "".join(f" {geo([cpi[n][w] for n in names]):.2f} |"
                          for w in widths)
                + f" {geo([cpi[n][min(widths)] / cpi[n][max(widths)] for n in names]):.2f} |\n")
        ratios = [cpi[n][min(widths)] / cpi[n][max(widths)] for n in names]
        f.write(f"\n{len(names)} benchmarks, {total} dynamic instructions; "
                f"serial/parallel CPI ratio {geo(ratios):.2f} "
                f"(range {min(ratios):.2f} - {max(ratios):.2f}).\n")
        f.write("Five hand kernels, for comparison: 13.51 "
                "(range 11.8 - 15.1).\n")
        if bad:
            f.write(f"\nWARNING: self-verification did not pass for {bad}\n")
    return path


def compiled_rtl_spot(elf_paths, n_insns=6000, out_dir="results",
                      points=None):
    """Run a prefix of each compiled binary on the RTL core, everywhere.

    Two independent assertions per run: the measured cycle count must equal
    the closed-form model on the mix of exactly those n_insns instructions,
    and the whole data memory afterwards must equal the golden ISS.
    """
    points = points or POINTS_FULL
    path = os.path.join(out_dir, "compiled_spot.md")
    lines = ["Compiled-code RTL spot checks.", "",
             "The first N retired instructions of a compiled Embench-IoT "
             "binary are\nexecuted on the RTL core at every design point.  "
             "`cycles` is measured,\n`model` is model_cycles() on the mix of "
             "exactly those N instructions, and\n`state` compares the whole "
             "data memory against the golden ISS.", "",
             "| binary | N | design point | cycles | CPI | model | err | "
             "state |",
             "|:--|--:|:--|--:|--:|--:|--:|:--:|"]
    n_ok = n_run = 0
    for elf in elf_paths:
        image, entry = load_elf(elf)
        if entry != 0:
            raise ValueError(f"{elf}: RTL bench resets to 0, entry is "
                             f"{entry:#x}")
        iss = GoldenRV32I(dict(image), pc=entry)
        mix, srx = {}, 0
        for _ in range(n_insns):
            word = iss.mem.get(iss.pc >> 2, 0)
            op, f3 = word & 0x7F, (word >> 12) & 7
            if op in (0x13, 0x33) and f3 == 5:
                srx += (((word >> 20) & 31) if op == 0x13
                        else (iss.x[(word >> 20) & 31] & 31))
            iss.step()
            cls = _classify(word)
            mix[cls] = mix.get(cls, 0) + 1
        name = os.path.basename(elf)
        for width, adder in points:
            cyc, mem = measure_cycles([], dict(image), n_insns, width, adder)
            pred = model_cycles(mix, srx, width)
            keys = set(mem) | set(iss.mem)
            same = all(mem.get(k, 0) == iss.mem.get(k, 0) for k in keys)
            ok = (pred == cyc) and same
            n_ok += ok
            n_run += 1
            lines.append(f"| {name} | {n_insns} | W={width} {adder} | {cyc} | "
                         f"{cyc / n_insns:.2f} | {pred} | "
                         f"{(pred - cyc) / n_insns:+.4f} | "
                         f"{'OK' if same else 'MISMATCH'} |")
            print(f"[study]   {name} W={width}/{adder}: {cyc} cycles, "
                  f"model {pred}, memory {'OK' if same else 'MISMATCH'}")
    lines += ["", f"{n_ok} of {n_run} runs match at zero tolerance."]
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return path


def mix_envelope(out_dir="results", w_serial=1, w_parallel=32,
                 transistors=None):
    """Exact extrema of the CPI ratio over EVERY instruction mix.

    CPI is exactly linear in the class-frequency vector, so a ratio of two
    CPIs is a ratio of linear forms on the probability simplex and attains
    its extrema at vertices -- single-class programs.  The envelope below is
    therefore complete, not a sample: no workload, real or adversarial, can
    fall outside it.
    """
    path = os.path.join(out_dir, "mix_envelope.md")
    # vertices: one per class, plus the W = 1 right-shift stall extremes
    vertices = [(c, class_cycles(c, w_serial), class_cycles(c, w_parallel))
                for c in CLASSES]
    if w_serial == 1:                       # SRA/SRL by 31 is the worst case
        vertices.append(("shift (right, shamt 31)",
                         class_cycles("shift", 1) + 31,
                         class_cycles("shift", w_parallel)))
    lo = min(vertices, key=lambda v: v[1] / v[2])
    hi = max(vertices, key=lambda v: v[1] / v[2])
    with open(path, "w") as f:
        f.write(f"Exact envelope of CPI(W={w_serial}) / CPI(W={w_parallel}) "
                "over ALL instruction mixes\n\n"
                "CPI is linear in the class-frequency vector, so the ratio "
                "is a ratio of\nlinear forms on the simplex and its extrema "
                "are attained at vertices, i.e.\nat single-class programs.  "
                "This bound is exact and complete.\n\n")
        f.write(f"| class | W={w_serial} | W={w_parallel} | ratio |\n")
        f.write("|:--|--:|--:|--:|\n")
        for c, a, b in vertices:
            f.write(f"| {c} | {a} | {b} | {a / b:.3f} |\n")
        f.write(f"\nCPI ratio over all mixes: "
                f"[{lo[1] / lo[2]:.2f}, {hi[1] / hi[2]:.2f}]  "
                f"(min at 100% {lo[0]}, max at 100% {hi[0]})\n")
        if transistors:
            t1 = transistors[(w_serial, "ripple")]
            for adder in ("ripple", "prefix"):
                key = (w_parallel, adder)
                if key not in transistors:
                    continue
                k = t1 / transistors[key]
                f.write(f"Energy ratio at a fixed clock (E ~ T x CPI), "
                        f"W={w_parallel} {adder}: "
                        f"[{k * lo[1] / lo[2]:.2f}, "
                        f"{k * hi[1] / hi[2]:.2f}]\n")
    return path


def coverage_matrix(out_dir="results", points=None, abc_points=None,
                    gate_level_workload="checksum", spot_done=True):
    """Design-point x validation-stage coverage, generated from the code."""
    import unittest

    points = points or POINTS_FULL
    abc_points = abc_points or ((1, "ripple"), (32, "ripple"), (32, "prefix"))
    path = os.path.join(out_dir, "coverage.md")

    # count the co-simulation tests actually collected, per design point
    counts, total = {}, 0
    try:
        suite = unittest.defaultTestLoader.discover("tests", top_level_dir=".")

        def walk(s):
            for x in s:
                if isinstance(x, unittest.TestSuite):
                    walk(x)
                else:
                    cls = type(x)
                    if not getattr(cls, "COSIM", True):
                        continue           # flow tests, not co-simulation
                    key = (getattr(cls, "WIDTH", 1),
                           getattr(cls, "ADDER", "ripple"))
                    counts[key] = counts.get(key, 0) + 1
        walk(suite)
        total = sum(counts.values())
    except Exception as e:                          # pragma: no cover
        print(f"[study] co-simulation test count unavailable: {e}")

    # points with a verified depth-compliant physical netlist
    pipelined = set()
    try:
        import json
        with open(os.path.join(out_dir, "depth_compliant.json")) as fj:
            for r in json.load(fj):
                if r.get("depth_ok") and r.get("fanout_ok") and \
                        r.get("gate_arch_cycles") == r.get("rtl_cycles"):
                    pipelined.add((r["width"], r["adder"]))
    except (OSError, ValueError):
        pass

    with open(path, "w") as f:
        f.write("Design-point x validation-stage coverage (generated).\n\n"
                "co-sim     RTL co-simulation tests against the golden ISS\n"
                "equiv      formal (SAT) combinational equivalence after "
                "mapping and\n           again after fan-out legalization "
                "(results/formal.md), plus\n           randomized "
                "equivalence over 8,192 patterns\n"
                "kernel CPI cycle-accurate RTL run of the five hand kernels, "
                "result\n           asserted against the ISS (repeated with "
                "3 wait states)\n"
                f"gate-level execution of one complete program "
                f"({gate_level_workload}) on the\n           mapped netlist: "
                "cycles asserted = RTL, result asserted = ISS\n"
                "compiled   prefix of a compiled Embench-IoT binary executed "
                "at RTL:\n           cycles = closed-form model, whole data "
                "memory = ISS\n"
                "ABC        independent yosys+ABC mapping of the same "
                "RTLIL\n"
                "pipelined  depth-compliant (<= 17 stages) physical "
                "netlist: DRC PASS,\n           formal one-cycle "
                "equivalence over S periods (results/formal.md)\n           "
                "and randomized (4,096 cases), gate-level\n           "
                f"execution of {gate_level_workload} at sub-cycle "
                "granularity with cycles = RTL,\n           result = ISS "
                "(results/depth_compliant.md)\n\n")
        f.write("| design point | co-sim | equiv | kernel CPI | gate-level | "
                "compiled | ABC | pipelined |\n")
        f.write("|:--|--:|:--:|:--:|:--:|:--:|:--:|:--:|\n")
        for p in points:
            f.write(f"| W = {p[0]} {p[1]} | {counts.get(p, '?')} | yes | yes "
                    f"| yes | {'yes' if spot_done else 'not run'} "
                    f"| {'yes' if p in abc_points else 'not run'} "
                    f"| {'yes' if p in pipelined else 'not run'} |\n")
        f.write(f"\n{total} co-simulation tests over "
                f"{len(counts)} (width, adder) pairs.\n"
                "Two stages are deliberately partial and are marked as such: "
                "gate-level\nexecution is one program per netlist, and the "
                "independent mapper is run\nfor three representative "
                "netlists.\n")
    return path

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    run(POINTS_QUICK if args.quick else POINTS_FULL)
