"""Simulation wrapper: M2D core + external digit-serial register file."""

from amaranth import *
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from .core import M2D
from .units.regfile import SerialRegisterFile


__all__ = ["M2DSim"]


class M2DSim(wiring.Component):
    """Core with the external register file attached, for simulation and
    for whole-system synthesis experiments."""

    ibus_addr: Out(32)
    ibus_cyc:  Out(1)
    ibus_ack:  In(1)
    ibus_rdat: In(32)

    dbus_addr: Out(32)
    dbus_cyc:  Out(1)
    dbus_we:   Out(1)
    dbus_sel:  Out(4)
    dbus_wdat: Out(32)
    dbus_ack:  In(1)
    dbus_rdat: In(32)

    def __init__(self, width=1, adder="ripple", reset_address=0x0000_0000):
        super().__init__()
        self.cpu = M2D(width=width, adder=adder,
                       reset_address=reset_address)
        self.rf  = SerialRegisterFile(width=width)

    def elaborate(self, platform):
        m = Module()
        m.submodules.cpu = cpu = self.cpu
        m.submodules.rf  = rf  = self.rf

        m.d.comb += [
            self.ibus_addr.eq(cpu.ibus_addr),
            self.ibus_cyc .eq(cpu.ibus_cyc),
            cpu.ibus_ack  .eq(self.ibus_ack),
            cpu.ibus_rdat .eq(self.ibus_rdat),

            self.dbus_addr.eq(cpu.dbus_addr),
            self.dbus_cyc .eq(cpu.dbus_cyc),
            self.dbus_we  .eq(cpu.dbus_we),
            self.dbus_sel .eq(cpu.dbus_sel),
            self.dbus_wdat.eq(cpu.dbus_wdat),
            cpu.dbus_ack  .eq(self.dbus_ack),
            cpu.dbus_rdat .eq(self.dbus_rdat),

            rf.raddr1     .eq(cpu.rf_raddr1),
            rf.raddr2     .eq(cpu.rf_raddr2),
            rf.index      .eq(cpu.rf_index),
            cpu.rf_rdig1  .eq(rf.rdig1),
            cpu.rf_rdig2  .eq(rf.rdig2),
            rf.wen        .eq(cpu.rf_wen),
            rf.waddr      .eq(cpu.rf_waddr),
            rf.wdig       .eq(cpu.rf_wdig),
        ]
        return m
