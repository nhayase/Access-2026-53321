"""
M2D: a width-parameterized digit-serial RV32I core for
2D-semiconductor (MoS2) VLSI design-space exploration.

The core processes ``width`` bits of the 32-bit datapath per clock cycle
("digit-serial"):

  * ``width = 1``   -- the bit-serial design point of RV32-WUJI
    (Ao et al., Nature 640, 654 (2025)) / SERV: minimum transistor count,
    32 cycles per execution stage.
  * ``width = 32``  -- a fully parallel single-issue multi-cycle datapath:
    every execution stage takes one cycle.
  * intermediate widths (2/4/8/16) trade transistors against cycles.

The digit adders (ALU, PC, comparator) are selectable between a ripple
carry chain (O(W) stages, minimum transistors) and a structural Brent-Kung
parallel-prefix adder (O(log W) stages, max prefix fan-out 2); see
``m2d.units.adders``.  Together the two parameters span the
microarchitectural question this repository quantifies: *where is the
optimal RISC-V design point under 2D-semiconductor constraints, and does
parallel (multi-bit, parallel-carry) arithmetic pay off?*

Fixed architectural decisions shared by every design point (so that the
comparison isolates datapath width and adder structure):

  * FSM ``FETCH -> DECODE -> [EXEC1] -> [MEM] -> EXEC2``; branches, JALR,
    SLT and shifts take two execution stages, loads/stores go through MEM
    (paper, Extended Data Table 1).
  * The PC is a rotating shift register advancing ``width`` bits per
    execution cycle (for width = 32 the rotation degenerates into a plain
    parallel register write).
  * The register file is *external* and accessed ``width`` bits per cycle
    (paper: only interface modules live on the chip).
  * Shifts: at width = 1 right shifts pre-rotate the buffer register for
    ``shamt`` cycles and left shifts reuse the same countdown for the low
    zero fill (the transistor-minimal RV32-WUJI scheme).  At width > 1 the
    shift is performed in one step by a combinational barrel shifter on the
    buffer register at the EXEC1 -> EXEC2 transition.
  * 37 RV32I instructions (no CSR/exceptions; FENCE would be a NOP);
    naturally aligned memory accesses are assumed.

Module structure mirrors Fig. 5a of the paper (comments mark each block):

    State       digit counter + instruction state machine
    Ctrl        program counter (digit-serial PC adder)
    Decode      instruction decoding into control signals
    ImmDecode   immediate-number decoding (digit-serial output)
    Bufreg      32-bit shift/buffer register (addresses, shift data)
    ALU         W-bit digit-serial ALU (adder, logic, comparator)
    MEM_IF      memory interface + 32-bit dbus data register
    Regfile_IF  digit-serial register-file interface (register file external)
"""

from amaranth import *
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from .isa import Opcode, Funct3
from .units.adders import make_adder, ADDER_KINDS


__all__ = ["M2D", "WIDTHS"]

WIDTHS = (1, 2, 4, 8, 16, 32)


class M2D(wiring.Component):
    """Digit-serial RV32I core for MoS2 (2D semiconductor) implementation.

    Parameters
    ----------
    width : int
        Datapath digit width in bits (1, 2, 4, 8, 16 or 32).
    adder : str
        ``"ripple"`` (carry chain) or ``"prefix"`` (Brent-Kung).
    reset_address : int
        Reset vector.

    Bus protocol (both ibus and dbus): the core raises ``*_cyc`` with a valid
    address (and, for stores, write data/select) and holds it until the slave
    pulses ``*_ack`` together with valid read data.

    Register file protocol: the register file is external.  Each cycle of an
    execution stage the core presents ``rf_raddr1/2`` and the digit index
    ``rf_index``; the register file must return, combinationally, digit
    ``rf_index`` (``width`` bits, LSB-digit first) of rs1 and rs2 on
    ``rf_rdig1/2``.  Result digits are written back one per cycle through
    ``rf_wen``/``rf_waddr``/``rf_wdig`` at the same index.
    """

    def __init__(self, width=1, adder="ripple", reset_address=0x0000_0000):
        if width not in WIDTHS:
            raise ValueError(f"width must be one of {WIDTHS}, not {width}")
        if adder not in ADDER_KINDS:
            raise ValueError(f"adder must be one of {ADDER_KINDS}")
        self.width         = width
        self.digits        = 32 // width
        self.adder         = adder
        self.reset_address = reset_address
        iw = max(1, (self.digits - 1).bit_length())   # rf_index width
        super().__init__({
            # instruction bus
            "ibus_addr": Out(32),
            "ibus_cyc":  Out(1),
            "ibus_ack":  In(1),
            "ibus_rdat": In(32),
            # data bus
            "dbus_addr": Out(32),
            "dbus_cyc":  Out(1),
            "dbus_we":   Out(1),
            "dbus_sel":  Out(4),
            "dbus_wdat": Out(32),
            "dbus_ack":  In(1),
            "dbus_rdat": In(32),
            # external register file (digit-serial)
            "rf_raddr1": Out(5),
            "rf_raddr2": Out(5),
            "rf_index":  Out(iw),
            "rf_rdig1":  In(width),
            "rf_rdig2":  In(width),
            "rf_wen":    Out(1),
            "rf_waddr":  Out(5),
            "rf_wdig":   Out(width),
        })

    def elaborate(self, platform):
        m = Module()
        W      = self.width
        DIGITS = self.digits

        def adder(a, b, cin, name):
            return make_adder(m, self.adder, a, b, cin, name)

        # ================================================================
        # State  -- digit counter + instruction state machine (paper Fig. 5c)
        # ================================================================
        if DIGITS > 1:
            cnt      = Signal(range(DIGITS), reset_less=True)
            cnt_done = Signal()
            cnt_is0  = Signal()
            m.d.comb += [
                cnt_done.eq(cnt == DIGITS - 1),
                cnt_is0 .eq(cnt == 0),
            ]
        else:
            cnt      = Signal(1)        # constant 0: single-digit datapath
            cnt_done = C(1)
            cnt_is0  = C(1)

        def dig(sig32):
            """Current W-bit digit of a 32-bit value."""
            return sig32.word_select(cnt, W) if DIGITS > 1 else sig32

        # ================================================================
        # Ctrl -- program counter, kept as a *rotating shift register*.
        # During any execution stage that touches the PC it rotates once per
        # digit cycle: the current digit is always pc[0:W] and the updated
        # digit re-enters at the top.  After DIGITS rotations the register is
        # aligned again, so FETCH can read it in parallel.  This removes the
        # 32:1 read multiplexer and the 32-way write demultiplexer that an
        # indexed PC would need -- the RV32-WUJI/SERV transistor-count trick.
        # For W = 32 the rotation degenerates into a plain parallel write.
        # ================================================================
        pc = Signal(32, init=self.reset_address)

        # ================================================================
        # Decode -- instruction register and control signals
        #
        # Most datapath registers are `reset_less`: they are always written
        # (DECODE or a stage transition) before they are read, so wiring the
        # global reset to them only adds reset multiplexers.  Only the PC and
        # the FSM state register keep a reset, as in RV32-WUJI where the
        # register file and buffers are likewise external/uninitialised.
        # ================================================================
        ir     = Signal(32, reset_less=True)
        opcode = Signal(5)
        f3     = Signal(3)
        rd     = Signal(5)
        rs1    = Signal(5)
        rs2    = Signal(5)
        m.d.comb += [
            opcode.eq(ir[2:7]),
            rd    .eq(ir[7:12]),
            f3    .eq(ir[12:15]),
            rs1   .eq(ir[15:20]),
            rs2   .eq(ir[20:25]),
        ]

        is_lui    = Signal()
        is_auipc  = Signal()
        is_jal    = Signal()
        is_jalr   = Signal()
        is_branch = Signal()
        is_load   = Signal()
        is_store  = Signal()
        is_opimm  = Signal()
        is_op     = Signal()
        m.d.comb += [
            is_lui   .eq(opcode == Opcode.LUI),
            is_auipc .eq(opcode == Opcode.AUIPC),
            is_jal   .eq(opcode == Opcode.JAL),
            is_jalr  .eq(opcode == Opcode.JALR),
            is_branch.eq(opcode == Opcode.BRANCH),
            is_load  .eq(opcode == Opcode.LOAD),
            is_store .eq(opcode == Opcode.STORE),
            is_opimm .eq(opcode == Opcode.OP_IMM_32),
            is_op    .eq(opcode == Opcode.OP_32),
        ]

        is_mem   = Signal()
        is_regop = Signal()
        is_slt   = Signal()   # SLT/SLTU/SLTI/SLTIU
        is_sll   = Signal()
        is_srx   = Signal()   # SRL/SRA/SRLI/SRAI
        is_shift = Signal()
        is_alu   = Signal()   # ADD/SUB/XOR/OR/AND (+imm forms)
        sub      = Signal()
        sra      = Signal()
        m.d.comb += [
            is_mem  .eq(is_load | is_store),
            is_regop.eq(is_op | is_opimm),
            is_slt  .eq(is_regop & ~f3[2] & f3[1]),        # funct3 = 010/011
            is_sll  .eq(is_regop & (f3 == Funct3.SLL)),
            is_srx  .eq(is_regop & (f3 == Funct3.SR)),
            is_shift.eq(is_sll | is_srx),
            is_alu  .eq(is_regop & ~is_slt & ~is_shift),
            sub     .eq(is_op & (f3 == Funct3.ADD) & ir[30]),
            sra     .eq(is_srx & ir[30]),
        ]

        # Two-stage instructions (paper: shift, mem, branch and slt require
        # several stages; JALR needs rs1+imm before the PC can be updated).
        two_stage = Signal()
        m.d.comb += two_stage.eq(is_branch | is_jalr | is_slt | is_shift)

        rd_we = Signal()
        m.d.comb += rd_we.eq(
            (is_lui | is_auipc | is_jal | is_jalr | is_load | is_regop)
            & (rd != 0))

        # PC := PC+4 can complete during EXEC1 for these classes, in parallel
        # with address computation / operand capture / comparison.
        pc_in_exec1 = Signal()
        m.d.comb += pc_in_exec1.eq(is_mem | is_slt | is_shift)

        cmp_unsigned = Signal()
        m.d.comb += cmp_unsigned.eq(Mux(is_branch, f3[1], f3[0]))

        # ================================================================
        # ImmDecode -- immediate-number decoding, emitted digit-serially
        # ================================================================
        imm_i = Signal(signed(32))
        imm_s = Signal(signed(32))
        imm_b = Signal(signed(32))
        imm_u = Signal(signed(32))
        imm_j = Signal(signed(32))
        m.d.comb += [
            imm_i.eq(Cat(ir[20:31], ir[31].replicate(21)).as_signed()),
            imm_s.eq(Cat(ir[7:12], ir[25:31], ir[31].replicate(21)).as_signed()),
            imm_b.eq(Cat(C(0, 1), ir[8:12], ir[25:31], ir[7],
                         ir[31].replicate(20)).as_signed()),
            imm_u.eq(Cat(C(0, 12), ir[12:32]).as_signed()),
            imm_j.eq(Cat(C(0, 1), ir[21:31], ir[20], ir[12:20],
                         ir[31].replicate(12)).as_signed()),
        ]
        imm = Signal(32)
        with m.Switch(opcode):
            with m.Case(Opcode.LUI, Opcode.AUIPC):
                m.d.comb += imm.eq(imm_u)
            with m.Case(Opcode.JAL):
                m.d.comb += imm.eq(imm_j)
            with m.Case(Opcode.BRANCH):
                m.d.comb += imm.eq(imm_b)
            with m.Case(Opcode.STORE):
                m.d.comb += imm.eq(imm_s)
            with m.Default():               # JALR, LOAD, OP-IMM
                m.d.comb += imm.eq(imm_i)
        imm_dig = Signal(W)
        m.d.comb += imm_dig.eq(dig(imm))

        # ================================================================
        # Regfile_IF -- digit-serial access to the external register file
        # ================================================================
        m.d.comb += [
            self.rf_raddr1.eq(rs1),
            self.rf_raddr2.eq(rs2),
            self.rf_waddr .eq(rd),
        ]
        if DIGITS > 1:
            m.d.comb += self.rf_index.eq(cnt)
        a_dig = Signal(W)   # serial Op_a (rs1)
        b_rf  = Signal(W)   # serial rs2
        m.d.comb += [
            a_dig.eq(self.rf_rdig1),
            b_rf .eq(self.rf_rdig2),
        ]

        # ================================================================
        # Bufreg -- 32-bit shift/buffer register
        #   EXEC1: accumulates rs1+imm (addresses, JALR target) or rs1
        #          (shift operand); EXEC2: shifts out.
        # ================================================================
        bufreg = Signal(32, reset_less=True)

        # ================================================================
        # MEM_IF -- 32-bit dbus data register + byte-lane logic
        # (also captures rs2 during EXEC1 of register-operand shifts, so
        #  that the shift amount needs no dedicated capture register)
        # ================================================================
        memdat = Signal(32, reset_less=True)

        loff = Signal(2)   # low address bits of the computed address
        m.d.comb += loff.eq(bufreg[0:2])

        # store write data / byte select (replicate lanes, RV32 convention)
        st_wdat = Signal(32)
        st_sel  = Signal(4)
        with m.Switch(f3):
            with m.Case(Funct3.B):
                m.d.comb += [
                    st_wdat.eq(memdat[0:8].replicate(4)),
                    st_sel .eq(C(0b0001, 4) << loff),
                ]
            with m.Case(Funct3.H):
                m.d.comb += [
                    st_wdat.eq(memdat[0:16].replicate(2)),
                    st_sel .eq(Mux(loff[1], C(0b1100, 4), C(0b0011, 4))),
                ]
            with m.Default():
                m.d.comb += [
                    st_wdat.eq(memdat),
                    st_sel .eq(C(0b1111, 4)),
                ]

        # load lane select + sign/zero extension
        ld_byte = Signal(8)
        ld_half = Signal(16)
        ld_ext  = Signal(32)
        m.d.comb += [
            ld_byte.eq(self.dbus_rdat.word_select(loff, 8)),
            ld_half.eq(self.dbus_rdat.word_select(loff[1], 16)),
        ]
        with m.Switch(f3):
            with m.Case(Funct3.B):
                m.d.comb += ld_ext.eq(Cat(ld_byte, ld_byte[7].replicate(24)))
            with m.Case(Funct3.BU):
                m.d.comb += ld_ext.eq(ld_byte)
            with m.Case(Funct3.H):
                m.d.comb += ld_ext.eq(Cat(ld_half, ld_half[15].replicate(16)))
            with m.Case(Funct3.HU):
                m.d.comb += ld_ext.eq(ld_half)
            with m.Default():
                m.d.comb += ld_ext.eq(self.dbus_rdat)

        m.d.comb += [
            self.dbus_addr.eq(Cat(C(0, 2), bufreg[2:32])),
            self.dbus_we  .eq(is_store),
            self.dbus_sel .eq(st_sel),
            self.dbus_wdat.eq(st_wdat),
        ]

        # next-cycle value of memdat during EXEC1 capture; also read
        # combinationally at the EXEC1 -> EXEC2 transition to obtain the
        # shift amount of register-operand shifts (rs2[4:0]) without a
        # dedicated shamt register.
        memdat_nx = Signal(32)
        m.d.comb += memdat_nx.eq(Cat(memdat[W:], b_rf))

        shamt_eff = Signal(5)   # valid during the EXEC1 cnt_done cycle
        m.d.comb += shamt_eff.eq(Mux(is_op, memdat_nx[0:5], ir[20:25]))

        # ================================================================
        # ALU -- W-bit digit-serial ALU
        # ================================================================
        carry_alu = Signal(reset_less=True)   # inter-digit adder carry
        carry_pc  = Signal(reset_less=True)   # inter-digit PC adder carry
        eq_r      = Signal(reset_less=True)   # running equality (comparator)
        ltu_r     = Signal(reset_less=True)   # running unsigned less-than

        # comparison operand (branches: rs2; slt: rs2 or immediate)
        b_cmp = Signal(W)
        m.d.comb += b_cmp.eq(Mux(is_op | is_branch, b_rf, imm_dig))

        # digit comparator: equality is a W-bit XNOR reduction; the digit
        # unsigned less-than reuses the selected adder architecture as a
        # subtractor (lt = ~carry_out(a + ~b + 1)), so that "parallel
        # addition" also means parallel comparison.
        eq_now = Signal()
        lt_now = Signal()
        m.d.comb += eq_now.eq(a_dig == b_cmp)
        _, cmp_co = adder(a_dig, ~b_cmp, C(1), "cmp")
        m.d.comb += lt_now.eq(~cmp_co)

        # comparator finals, valid at the cnt_done cycle of EXEC1
        eq_f  = Signal()
        ltu_f = Signal()
        lts_f = Signal()
        lt_f  = Signal()
        a_msb = Signal()
        b_msb = Signal()
        m.d.comb += [
            a_msb.eq(a_dig[W - 1]),
            b_msb.eq(b_cmp[W - 1]),
            eq_f .eq(eq_r & eq_now),
            ltu_f.eq(Mux(eq_now, ltu_r, lt_now)),
            # at the MSB digit: if signs differ, a < b iff a is negative
            lts_f.eq(Mux(a_msb ^ b_msb, a_msb, ltu_f)),
            lt_f .eq(Mux(cmp_unsigned, ltu_f, lts_f)),
        ]

        cond_met = Signal(reset_less=True)   # latched branch condition
        slt_res  = Signal(reset_less=True)   # latched slt result

        branch_taken = Signal()
        with m.Switch(f3):
            with m.Case(Funct3.BEQ):
                m.d.comb += branch_taken.eq(eq_f)
            with m.Case(Funct3.BNE):
                m.d.comb += branch_taken.eq(~eq_f)
            with m.Case(Funct3.BLT):
                m.d.comb += branch_taken.eq(lts_f)
            with m.Case(Funct3.BGE):
                m.d.comb += branch_taken.eq(~lts_f)
            with m.Case(Funct3.BLTU):
                m.d.comb += branch_taken.eq(ltu_f)
            with m.Default():   # BGEU
                m.d.comb += branch_taken.eq(~ltu_f)

        # ---- EXEC1 digit adder: rs1 + imm (addresses / JALR target), or
        #      rs1 + 0 (shift-operand capture into Bufreg)
        b1_dig = Signal(W)
        m.d.comb += b1_dig.eq(Mux(is_shift, 0, imm_dig))
        sum1, c1_out = adder(a_dig, b1_dig, carry_alu, "alu1")

        # completing value of Bufreg at the EXEC1 cnt_done cycle (= rs1 for
        # shifts, rs1+imm otherwise); input of the barrel shifter at W > 1
        bufreg_nx = Signal(32)
        m.d.comb += bufreg_nx.eq(Cat(bufreg[W:], sum1))

        # ---- EXEC2 digit adder operands
        # The PC rotates during serial access, so the current digit is pc[0:W].
        pc_dig = Signal(W)
        m.d.comb += pc_dig.eq(pc[0:W])

        four      = Signal(32)
        plus4_dig = Signal(W)
        m.d.comb += [
            four.eq(4),
            plus4_dig.eq(dig(four)),   # constant 4, digit-serial
        ]

        a2 = Signal(W)
        b2 = Signal(W)
        m.d.comb += [
            a2.eq(Mux(is_auipc | is_jal | is_jalr, pc_dig, a_dig)),
            b2.eq(Mux(is_jal | is_jalr, plus4_dig,
                  Mux(is_auipc, imm_dig,
                  Mux(is_op, b_rf ^ sub.replicate(W),
                      imm_dig ^ sub.replicate(W))))),
        ]
        sum2, c2_out = adder(a2, b2, carry_alu, "alu2")

        # logic operand (never inverted by `sub`)
        b_logic = Signal(W)
        m.d.comb += b_logic.eq(Mux(is_op, b_rf, imm_dig))

        if W == 1:
            # right shifts stall the counter for `shamt` cycles first
            # ("right shifts delay sending an output until the shift is
            # complete"); left shifts reuse the same countdown so that the
            # wide comparison `cnt >= shamt` collapses into a zero test.
            shift_delay  = Signal(5, reset_less=True)
            delay_active = Signal()
            sll_pass     = Signal()   # SLL: past the low zero-fill region
            m.d.comb += [
                delay_active.eq(is_srx & (shift_delay != 0)),
                sll_pass    .eq(shift_delay == 0),
            ]
            shift_dig = Signal(W)
            m.d.comb += shift_dig.eq(
                  (is_sll & sll_pass & bufreg[0])
                | (is_srx            & bufreg[0]))
        else:
            # W > 1: the shift was applied in one step by the barrel shifter
            # at the EXEC1 -> EXEC2 transition; EXEC2 just streams Bufreg.
            shift_dig = Signal(W)
            m.d.comb += shift_dig.eq(bufreg[0:W])

        # ---- result-digit multiplexer (Op_a op Op_b, W bits per cycle).
        # The selects are mutually exclusive (decoded from one opcode), so a
        # one-hot AND-OR network is used instead of an If/Elif priority
        # chain; the AOI/OAI covering of the mapper then absorbs it.
        alu_dig = Signal(W)
        with m.Switch(f3):
            with m.Case(Funct3.XOR):
                m.d.comb += alu_dig.eq(a_dig ^ b_logic)
            with m.Case(Funct3.OR):
                m.d.comb += alu_dig.eq(a_dig | b_logic)
            with m.Case(Funct3.AND):
                m.d.comb += alu_dig.eq(a_dig & b_logic)
            with m.Default():               # ADD/SUB
                m.d.comb += alu_dig.eq(sum2)

        slt_dig = Signal(W)
        m.d.comb += slt_dig.eq(Mux(cnt_is0, slt_res, 0))  # zero-extended

        res_dig = Signal(W)
        m.d.comb += res_dig.eq(
              (is_lui.replicate(W)                        & imm_dig)
            | ((is_auipc | is_jal | is_jalr).replicate(W) & sum2)
            | (is_slt.replicate(W)                        & slt_dig)
            | (is_shift.replicate(W)                      & shift_dig)
            | (is_load.replicate(W)                       & memdat[0:W])
            | (is_alu.replicate(W)                        & alu_dig))

        # ---- Ctrl: digit-serial PC adder (PC + 4 / PC + imm)
        pcb = Signal(W)
        pc_sum, pc_co = adder(pc_dig, pcb, carry_pc, "pcadd")

        # ---- Bufreg shift fill (W = 1 arithmetic shifts keep the sign bit)
        buf_fill = Signal(W)
        if W == 1:
            m.d.comb += buf_fill.eq(Mux(sra, bufreg[31], 0))

        # JALR target digit: bit 0 of the target is cleared (RV32I)
        jalr_dig = Signal(W)
        if W == 1:
            m.d.comb += jalr_dig.eq(Mux(cnt_is0, 0, bufreg[0]))
        else:
            m.d.comb += jalr_dig.eq(Mux(cnt_is0,
                                        Cat(C(0, 1), bufreg[1:W]),
                                        bufreg[0:W]))

        # ================================================================
        # State machine (paper Fig. 5c: Fetch / Decode / stage 1 / stage 2)
        # ================================================================
        def exec2_body():
            """EXEC2 datapath actions of one digit cycle (shared between the
            W = 1 delay-gated body and the plain W > 1 body)."""
            if DIGITS > 1:
                m.d.sync += cnt.eq(cnt + 1)

            # digit-serial writeback to the external register file
            m.d.comb += [
                self.rf_wen .eq(rd_we),
                self.rf_wdig.eq(res_dig),
            ]

            # Bufreg shift-out
            if W == 1:
                with m.If(is_jalr | is_srx | (is_sll & sll_pass)):
                    m.d.sync += bufreg.eq(Cat(bufreg[1:], buf_fill))
                with m.If(is_sll & ~sll_pass):
                    m.d.sync += shift_delay.eq(shift_delay - 1)
            else:
                with m.If(is_jalr | is_shift):
                    m.d.sync += bufreg.eq(Cat(bufreg[W:], C(0, W)))
            with m.If(is_load):
                m.d.sync += memdat.eq(Cat(memdat[W:], C(0, W)))

            # Ctrl: next-PC computation (unless done in EXEC1)
            with m.If(~pc_in_exec1):
                with m.If(is_jalr):
                    # PC := (rs1 + imm) & ~1, from Bufreg
                    m.d.sync += pc.eq(Cat(pc[W:], jalr_dig))
                with m.Else():
                    m.d.comb += pcb.eq(
                        Mux(is_jal | (is_branch & cond_met),
                            imm_dig, plus4_dig))
                    m.d.sync += [
                        pc.eq(Cat(pc[W:], pc_sum)),   # rotate once
                        carry_pc.eq(pc_co),
                    ]

            # ALU adder carry
            m.d.sync += carry_alu.eq(c2_out)

            with m.If(cnt_done):
                m.next = "FETCH"

        with m.FSM():

            with m.State("FETCH"):
                m.d.comb += [
                    self.ibus_addr.eq(pc),
                    self.ibus_cyc .eq(1),
                ]
                with m.If(self.ibus_ack):
                    m.d.sync += ir.eq(self.ibus_rdat)
                    m.next = "DECODE"

            with m.State("DECODE"):
                m.d.sync += [
                    carry_alu.eq(sub),   # two's-complement subtraction
                    carry_pc .eq(0),
                    eq_r     .eq(1),
                    ltu_r    .eq(0),
                ]
                if DIGITS > 1:
                    m.d.sync += cnt.eq(0)
                with m.If(is_mem | two_stage):
                    m.next = "EXEC1"
                with m.Else():
                    m.next = "EXEC2"

            # ---- first execution stage: DIGITS cycles --------------------
            with m.State("EXEC1"):
                if DIGITS > 1:
                    m.d.sync += cnt.eq(cnt + 1)

                # serial address/operand accumulation into Bufreg
                with m.If(is_jalr | is_mem | is_shift):
                    m.d.sync += [
                        bufreg   .eq(bufreg_nx),
                        carry_alu.eq(c1_out),
                    ]

                # store data capture into the MEM_IF data register; shifts
                # with a register operand capture rs2 the same way, so that
                # rs2[4:0] is available as the shift amount at the end.
                with m.If(is_store | (is_shift & is_op)):
                    m.d.sync += memdat.eq(memdat_nx)

                # serial comparator
                with m.If(is_branch | is_slt):
                    m.d.sync += [
                        eq_r .eq(eq_r & eq_now),
                        ltu_r.eq(Mux(eq_now, ltu_r, lt_now)),
                    ]

                # PC := PC + 4 in parallel (mem / slt / shift)
                with m.If(pc_in_exec1):
                    m.d.comb += pcb.eq(plus4_dig)
                    m.d.sync += [
                        pc.eq(Cat(pc[W:], pc_sum)),   # rotate once
                        carry_pc.eq(pc_co),
                    ]

                with m.If(cnt_done):
                    m.d.sync += [
                        carry_alu.eq(0),
                        carry_pc .eq(0),
                        cond_met .eq(branch_taken),
                        slt_res  .eq(lt_f),
                    ]
                    if DIGITS > 1:
                        m.d.sync += cnt.eq(0)
                    if W == 1:
                        m.d.sync += shift_delay.eq(
                            Mux(is_shift, shamt_eff, 0))
                    else:
                        # apply the whole shift in one step: combinational
                        # barrel shifter on the completed Bufreg value
                        # (overrides the accumulate assignment above)
                        shifted = Signal(32)
                        m.d.comb += shifted.eq(
                            Mux(is_sll, bufreg_nx << shamt_eff,
                            Mux(sra,
                                (bufreg_nx.as_signed()
                                 >> shamt_eff).as_unsigned(),
                                bufreg_nx >> shamt_eff)))
                        with m.If(is_shift):
                            m.d.sync += bufreg.eq(shifted)
                    with m.If(is_mem):
                        m.next = "MEM"
                    with m.Else():
                        m.next = "EXEC2"

            # ---- memory transaction ------------------------------------
            with m.State("MEM"):
                m.d.comb += self.dbus_cyc.eq(1)
                with m.If(self.dbus_ack):
                    with m.If(is_store):
                        m.next = "FETCH"
                    with m.Else():
                        m.d.sync += memdat.eq(ld_ext)
                        if DIGITS > 1:
                            m.d.sync += cnt.eq(0)
                        m.next = "EXEC2"

            # ---- final execution stage: DIGITS cycles --------------------
            # (W = 1: + `shamt` stall cycles for SRL/SRA)
            with m.State("EXEC2"):
                if W == 1:
                    with m.If(delay_active):
                        # pre-shift Bufreg without emitting output digits
                        m.d.sync += [
                            bufreg     .eq(Cat(bufreg[1:], buf_fill)),
                            shift_delay.eq(shift_delay - 1),
                        ]
                    with m.Else():
                        exec2_body()
                else:
                    exec2_body()

        return m
