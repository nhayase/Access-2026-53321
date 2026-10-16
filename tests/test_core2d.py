"""Instruction-set co-simulation of the M2D bit-serial core against a
Python golden-model ISS.

Every one of the 37 RV32-WUJI instructions is exercised with directed corner
cases, followed by randomized programs; after each run the architectural state
(x1..x31, PC, data memory) of the RTL is compared bit-exactly with the ISS.
"""

import random
import unittest

from amaranth.sim import Simulator

from m2d.sim import M2DSim
from . import rv32
from .rv32 import *   # noqa: F401,F403  (instruction encoders)
from .rv32 import GoldenRV32I, M32


def run_program(words, *, n_insns, data=None, timeout=400_000,
                width=1, adder="ripple"):
    """Execute `n_insns` instructions on the RTL, return (regs, pc, mem)."""
    dut = M2DSim(width=width, adder=adder)
    mem = {i: w & M32 for i, w in enumerate(words)}
    if data:
        mem.update(data)

    result = {}

    async def bench(ctx):
        retired = 0
        for _ in range(timeout):
            ctx.set(dut.ibus_ack, 0)
            ctx.set(dut.dbus_ack, 0)
            if ctx.get(dut.ibus_cyc):
                addr = ctx.get(dut.ibus_addr)
                ctx.set(dut.ibus_rdat, mem.get(addr >> 2, 0))
                ctx.set(dut.ibus_ack, 1)
                retired += 1
                if retired > n_insns:
                    break
            elif ctx.get(dut.dbus_cyc):
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
        else:
            raise TimeoutError("core did not retire enough instructions")

        result["regs"] = [ctx.get(r) for r in dut.rf.regs]
        result["pc"]   = ctx.get(dut.ibus_addr)
        result["mem"]  = dict(mem)

    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_testbench(bench)
    sim.run()
    return result


def run_golden(words, *, n_insns, data=None):
    mem = {i: w & M32 for i, w in enumerate(words)}
    if data:
        mem.update(data)
    iss = GoldenRV32I(mem, pc=0)
    for _ in range(n_insns):
        iss.step()
    return {"regs": list(iss.x), "pc": iss.pc, "mem": iss.mem}


class CoSimCase(unittest.TestCase):
    #: (datapath width, adder kind) of this test class; subclasses generated
    #: at the bottom of the file re-run the whole suite per design point.
    WIDTH = 1
    ADDER = "ripple"

    def cosim(self, words, n_insns, data=None):
        rtl = run_program(words, n_insns=n_insns, data=data,
                          width=self.WIDTH, adder=self.ADDER)
        ref = run_golden(words, n_insns=n_insns, data=data)
        self.assertEqual(rtl["pc"], ref["pc"], "PC mismatch")
        for i in range(1, 32):
            self.assertEqual(
                rtl["regs"][i], ref["regs"][i],
                f"x{i}: rtl={rtl['regs'][i]:#010x} ref={ref['regs'][i]:#010x}")
        keys = set(rtl["mem"]) | set(ref["mem"])
        for k in sorted(keys):
            self.assertEqual(rtl["mem"].get(k, 0), ref["mem"].get(k, 0),
                             f"mem[{k:#x}] mismatch")


class TestPaperDemo(CoSimCase):
    def test_1946_plus_25(self):
        """The arithmetic demo of the paper (Extended Data Fig. 7):
        1946 + 25 = 1971 and 1971 + 53 = 2024."""
        prog = [
            ADDI(1, 0, 1946),
            ADDI(2, 0, 25),
            ADD (3, 1, 2),      # 1971
            ADDI(4, 3, 53),     # 2024
            SW  (3, 0, 0x40),
            SW  (4, 0, 0x44),
        ]
        rtl = run_program(prog, n_insns=len(prog),
                          width=self.WIDTH, adder=self.ADDER)
        self.assertEqual(rtl["regs"][3], 1971)
        self.assertEqual(rtl["regs"][4], 2024)
        self.assertEqual(rtl["mem"][0x40 >> 2], 1971)
        self.assertEqual(rtl["mem"][0x44 >> 2], 2024)
        self.cosim(prog, len(prog))


class TestDirected(CoSimCase):
    def test_arith_logic(self):
        prog = [
            ADDI(1, 0, -2048), ADDI(2, 0, 2047),
            ADD(3, 1, 2), SUB(4, 1, 2), SUB(5, 2, 1),
            XOR(6, 1, 2), OR(7, 1, 2), AND(8, 1, 2),
            XORI(9, 1, -1), ORI(10, 1, 0x55), ANDI(11, 2, -256),
            ADDI(12, 0, 0), SUB(13, 12, 2),      # negative result
            ADD(14, 2, 2),
        ]
        self.cosim(prog, len(prog))

    def test_lui_auipc(self):
        prog = [
            LUI(1, 0xFFFFF), LUI(2, 0x12345), AUIPC(3, 0),
            AUIPC(4, 0x80000), AUIPC(5, 0xFFFFF),
        ]
        self.cosim(prog, len(prog))

    def test_slt(self):
        prog = [
            ADDI(1, 0, -5), ADDI(2, 0, 3),
            SLT(3, 1, 2), SLT(4, 2, 1), SLTU(5, 1, 2), SLTU(6, 2, 1),
            SLT(7, 1, 1), SLTU(8, 2, 2),
            SLTI(9, 1, -4), SLTI(10, 1, -6), SLTIU(11, 2, 4),
            SLTIU(12, 2, -1),      # sign-extended unsigned corner case
            LUI(13, 0x80000), SLT(14, 13, 2), SLTU(15, 13, 2),
        ]
        self.cosim(prog, len(prog))

    def test_shifts(self):
        prog = [
            LUI(1, 0x89ABC), ORI(1, 1, 0x5F & 0x7FF),
            ADDI(2, 0, 0), ADDI(3, 0, 1), ADDI(4, 0, 31), ADDI(5, 0, 17),
            SLLI(6, 1, 0), SLLI(7, 1, 1), SLLI(8, 1, 31), SLLI(9, 1, 13),
            SRLI(10, 1, 0), SRLI(11, 1, 1), SRLI(12, 1, 31), SRLI(13, 1, 9),
            SRAI(14, 1, 0), SRAI(15, 1, 1), SRAI(16, 1, 31), SRAI(17, 1, 11),
            SLL(18, 1, 4), SRL(19, 1, 4), SRA(20, 1, 4),
            SLL(21, 1, 2), SRL(22, 1, 5), SRA(23, 1, 5),
            ADDI(24, 0, 37), SLL(25, 1, 24),   # shamt = rs2[4:0] only
            SRA(26, 1, 24), SRL(27, 1, 24),
            ADDI(28, 0, 0x123), SRA(29, 28, 3),  # positive operand SRA
        ]
        self.cosim(prog, len(prog))

    def test_branches(self):
        prog = [
            ADDI(1, 0, -1), ADDI(2, 0, 1),
            BEQ(1, 2, 8),  ADDI(3, 0, 1), ADDI(4, 0, 2),   # not taken
            BNE(1, 2, 8),  ADDI(5, 0, 99),  ADDI(6, 0, 3), # taken, skip x5
            BLT(1, 2, 8),  ADDI(7, 0, 99),  ADDI(8, 0, 4), # taken (signed)
            BLTU(1, 2, 8), ADDI(9, 0, 5),  ADDI(10, 0, 6), # not taken (uns.)
            BGE(2, 1, 8),  ADDI(11, 0, 99), ADDI(12, 0, 7),# taken
            BGEU(1, 2, 8), ADDI(13, 0, 99), ADDI(14, 0, 8),# taken
            BEQ(2, 2, -8),                                  # backward: to x14
        ]
        # execution: 6 setup+branch pairs -> count carefully via golden model
        self.cosim(prog, 24)

    def test_jal_jalr(self):
        prog = [
            JAL(1, 12),          # 0x00 -> 0x0C, x1 = 4
            ADDI(2, 0, 99),      # skipped
            ADDI(3, 0, 5),       # 0x08 (jalr target)
            ADDI(4, 0, 7),       # 0x0C
            JALR(5, 0, 0x09),    # -> (0x09 & ~1) = 0x08, x5 = 0x14
            ADDI(6, 0, 11),      # 0x14? executed after return path
        ]
        # flow: 0x00 JAL -> 0x0C -> 0x10 JALR -> 0x08 -> 0x0C -> 0x10 JALR...
        self.cosim(prog, 5)

    def test_loads_stores(self):
        data = {0x100 >> 2: 0x8899AABB, 0x104 >> 2: 0x01234567}
        prog = [
            ADDI(1, 0, 0x100),
            LW(2, 1, 0), LW(3, 1, 4),
            LB(4, 1, 0), LB(5, 1, 1), LB(6, 1, 2), LB(7, 1, 3),
            LBU(8, 1, 0), LBU(9, 1, 3),
            LH(10, 1, 0), LH(11, 1, 2), LHU(12, 1, 0), LHU(13, 1, 6),
            SW(2, 1, 8),
            SB(4, 1, 12), SB(5, 1, 13), SB(6, 1, 14), SB(7, 1, 15),
            SH(10, 1, 16), SH(11, 1, 18),
            LW(14, 1, 12), LW(15, 1, 16),
            LB(16, 1, -4 & 0xFFF) if False else LW(16, 1, 8),
        ]
        self.cosim(prog, len(prog), data=data)

    def test_negative_offsets(self):
        data = {0x80 >> 2: 0xDEADBEEF}
        prog = [
            ADDI(1, 0, 0x90),
            LW(2, 1, -16),
            SW(2, 1, -8),
            LW(3, 1, -8),
        ]
        self.cosim(prog, len(prog), data=data)

    def test_x0_semantics(self):
        prog = [
            ADDI(0, 0, 123),        # write to x0 discarded
            ADD(1, 0, 0),
            ADDI(2, 0, 55),
            SUB(0, 2, 2),
            ADD(3, 0, 2),
        ]
        self.cosim(prog, len(prog))


class TestRandom(CoSimCase):
    def test_random_dataflow(self):
        """Randomized straight-line programs over the full ALU/shift/slt/mem
        instruction mix, co-simulated against the golden model."""
        rng = random.Random(20260808)
        gens = [
            lambda r: ADDI(r.randrange(32), r.randrange(32),
                           r.randrange(-2048, 2048)),
            lambda r: ADD (r.randrange(32), r.randrange(32), r.randrange(32)),
            lambda r: SUB (r.randrange(32), r.randrange(32), r.randrange(32)),
            lambda r: XOR (r.randrange(32), r.randrange(32), r.randrange(32)),
            lambda r: OR  (r.randrange(32), r.randrange(32), r.randrange(32)),
            lambda r: AND (r.randrange(32), r.randrange(32), r.randrange(32)),
            lambda r: SLT (r.randrange(32), r.randrange(32), r.randrange(32)),
            lambda r: SLTU(r.randrange(32), r.randrange(32), r.randrange(32)),
            lambda r: SLTI(r.randrange(32), r.randrange(32),
                           r.randrange(-2048, 2048)),
            lambda r: SLTIU(r.randrange(32), r.randrange(32),
                            r.randrange(-2048, 2048)),
            lambda r: XORI(r.randrange(32), r.randrange(32),
                           r.randrange(-2048, 2048)),
            lambda r: ORI (r.randrange(32), r.randrange(32),
                           r.randrange(-2048, 2048)),
            lambda r: ANDI(r.randrange(32), r.randrange(32),
                           r.randrange(-2048, 2048)),
            lambda r: SLLI(r.randrange(32), r.randrange(32), r.randrange(32)),
            lambda r: SRLI(r.randrange(32), r.randrange(32), r.randrange(32)),
            lambda r: SRAI(r.randrange(32), r.randrange(32), r.randrange(32)),
            lambda r: SLL (r.randrange(32), r.randrange(32), r.randrange(32)),
            lambda r: SRL (r.randrange(32), r.randrange(32), r.randrange(32)),
            lambda r: SRA (r.randrange(32), r.randrange(32), r.randrange(32)),
            lambda r: LUI (r.randrange(32), r.randrange(1 << 20)),
            # word-aligned scratch memory traffic at 0x200..0x23C
            lambda r: SW(r.randrange(32), 0, 0x200 + 4 * r.randrange(16)),
            lambda r: LW(r.randrange(32), 0, 0x200 + 4 * r.randrange(16)),
        ]
        prog = [gens[rng.randrange(len(gens))](rng) for _ in range(120)]
        self.cosim(prog, len(prog))


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# Design-point matrix: re-run the complete suite for every datapath width and
# for the Brent-Kung prefix adder at representative widths.  Class names show
# up in the unittest output as e.g. TestDirected_w8 / TestRandom_w32_prefix.
# ---------------------------------------------------------------------------

def _specialize(base, width, adder):
    tag = f"w{width}" + ("_prefix" if adder == "prefix" else "")
    name = f"{base.__name__}_{tag}"
    globals()[name] = type(name, (base,), {"WIDTH": width, "ADDER": adder})


# Every (width, adder) pair that the study reports is co-simulated.  The
# prefix adder used to be covered only at W = 8 and W = 32, which left
# W = 16 prefix -- the energy optimum of the depth-compliant comparison --
# without co-simulation coverage.  study.coverage_matrix() regenerates the
# table of what is covered where.
for _w in (2, 4, 8, 16, 32):
    for _base in (TestPaperDemo, TestDirected, TestRandom):
        _specialize(_base, _w, "ripple")
for _w in (2, 4, 8, 16, 32):
    for _base in (TestPaperDemo, TestDirected, TestRandom):
        _specialize(_base, _w, "prefix")
