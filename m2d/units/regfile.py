"""
Digit-serial register file for M2D.

In RV32-WUJI the 32x32 register file is *not* part of the 5,900-transistor
chip: the core only contains a register-file interface (Regfile_IF) and the
storage is accessed through a memory port (paper, Fig. 5b).  A 64-bit register
alone already costs 1,152 MoS2 transistors (paper, Supplementary Fig. 7), so
an on-chip 1,024-bit register file would be impractical at this integration
scale.

This component provides matching external storage for any datapath width:
combinational ``width``-bit reads of rs1/rs2 at digit ``index`` and a
``width``-bit digit write port, so that the core can read operands and write
back results one digit per clock cycle.  For ``width == 32`` it degenerates
into an ordinary 2R1W register file.
"""

from amaranth import *
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out


__all__ = ["SerialRegisterFile"]


class SerialRegisterFile(wiring.Component):

    def __init__(self, width=1):
        self.width  = width
        self.digits = 32 // width
        iw = max(1, (self.digits - 1).bit_length())
        super().__init__({
            "raddr1": In(5),
            "raddr2": In(5),
            "index":  In(iw),
            "rdig1":  Out(width),
            "rdig2":  Out(width),
            "wen":    In(1),
            "waddr":  In(5),
            "wdig":   In(width),
        })
        # x0 is hardwired to zero and never written.
        self.regs = [Signal(32, name=f"x{i}") for i in range(32)]

    def elaborate(self, platform):
        m = Module()
        W = self.width

        regs = Array(self.regs)
        if self.digits > 1:
            m.d.comb += [
                self.rdig1.eq(regs[self.raddr1].word_select(self.index, W)),
                self.rdig2.eq(regs[self.raddr2].word_select(self.index, W)),
            ]
        else:
            m.d.comb += [
                self.rdig1.eq(regs[self.raddr1]),
                self.rdig2.eq(regs[self.raddr2]),
            ]

        # per-digit write (static word_select per register, decoded enable)
        for i in range(1, 32):
            with m.If(self.wen & (self.waddr == i)):
                if self.digits > 1:
                    m.d.sync += self.regs[i].word_select(self.index, W) \
                                            .eq(self.wdig)
                else:
                    m.d.sync += self.regs[i].eq(self.wdig)

        return m
