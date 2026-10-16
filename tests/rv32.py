"""Minimal RV32I assembler + golden-model ISS for verifying M2D.

Covers exactly the 37 instructions of RV32-WUJI (Extended Data Table 1).
"""

M32 = 0xFFFF_FFFF


def _s(x, bits):
    x &= (1 << bits) - 1
    return x - (1 << bits) if x >> (bits - 1) else x


def sext32(x):
    return _s(x & M32, 32)

# ----------------------------------------------------------------- encoders

def _r(f7, rs2, rs1, f3, rd, op):
    return (f7 << 25) | (rs2 << 20) | (rs1 << 15) | (f3 << 12) | (rd << 7) | op

def _i(imm, rs1, f3, rd, op):
    return ((imm & 0xFFF) << 20) | (rs1 << 15) | (f3 << 12) | (rd << 7) | op

def _s_enc(imm, rs2, rs1, f3, op):
    imm &= 0xFFF
    return (((imm >> 5) & 0x7F) << 25) | (rs2 << 20) | (rs1 << 15) \
         | (f3 << 12) | ((imm & 0x1F) << 7) | op

def _b(imm, rs2, rs1, f3):
    imm &= 0x1FFF
    return (((imm >> 12) & 1) << 31) | (((imm >> 5) & 0x3F) << 25) \
         | (rs2 << 20) | (rs1 << 15) | (f3 << 12) \
         | (((imm >> 1) & 0xF) << 8) | (((imm >> 11) & 1) << 7) | 0x63

def _u(imm, rd, op):
    return (imm & 0xFFFFF000) | (rd << 7) | op

def _j(imm, rd):
    imm &= 0x1FFFFF
    return (((imm >> 20) & 1) << 31) | (((imm >> 1) & 0x3FF) << 21) \
         | (((imm >> 11) & 1) << 20) | (((imm >> 12) & 0xFF) << 12) \
         | (rd << 7) | 0x6F

LUI   = lambda rd, imm:            _u(imm << 12, rd, 0x37)
AUIPC = lambda rd, imm:            _u(imm << 12, rd, 0x17)
JAL   = lambda rd, off:            _j(off, rd)
JALR  = lambda rd, rs1, imm:       _i(imm, rs1, 0, rd, 0x67)
BEQ   = lambda rs1, rs2, off:      _b(off, rs2, rs1, 0)
BNE   = lambda rs1, rs2, off:      _b(off, rs2, rs1, 1)
BLT   = lambda rs1, rs2, off:      _b(off, rs2, rs1, 4)
BGE   = lambda rs1, rs2, off:      _b(off, rs2, rs1, 5)
BLTU  = lambda rs1, rs2, off:      _b(off, rs2, rs1, 6)
BGEU  = lambda rs1, rs2, off:      _b(off, rs2, rs1, 7)
LB    = lambda rd, rs1, imm:       _i(imm, rs1, 0, rd, 0x03)
LH    = lambda rd, rs1, imm:       _i(imm, rs1, 1, rd, 0x03)
LW    = lambda rd, rs1, imm:       _i(imm, rs1, 2, rd, 0x03)
LBU   = lambda rd, rs1, imm:       _i(imm, rs1, 4, rd, 0x03)
LHU   = lambda rd, rs1, imm:       _i(imm, rs1, 5, rd, 0x03)
SB    = lambda rs2, rs1, imm:      _s_enc(imm, rs2, rs1, 0, 0x23)
SH    = lambda rs2, rs1, imm:      _s_enc(imm, rs2, rs1, 1, 0x23)
SW    = lambda rs2, rs1, imm:      _s_enc(imm, rs2, rs1, 2, 0x23)
ADDI  = lambda rd, rs1, imm:       _i(imm, rs1, 0, rd, 0x13)
SLTI  = lambda rd, rs1, imm:       _i(imm, rs1, 2, rd, 0x13)
SLTIU = lambda rd, rs1, imm:       _i(imm, rs1, 3, rd, 0x13)
XORI  = lambda rd, rs1, imm:       _i(imm, rs1, 4, rd, 0x13)
ORI   = lambda rd, rs1, imm:       _i(imm, rs1, 6, rd, 0x13)
ANDI  = lambda rd, rs1, imm:       _i(imm, rs1, 7, rd, 0x13)
SLLI  = lambda rd, rs1, sh:        _r(0x00, sh, rs1, 1, rd, 0x13)
SRLI  = lambda rd, rs1, sh:        _r(0x00, sh, rs1, 5, rd, 0x13)
SRAI  = lambda rd, rs1, sh:        _r(0x20, sh, rs1, 5, rd, 0x13)
ADD   = lambda rd, rs1, rs2:       _r(0x00, rs2, rs1, 0, rd, 0x33)
SUB   = lambda rd, rs1, rs2:       _r(0x20, rs2, rs1, 0, rd, 0x33)
SLL   = lambda rd, rs1, rs2:       _r(0x00, rs2, rs1, 1, rd, 0x33)
SLT   = lambda rd, rs1, rs2:       _r(0x00, rs2, rs1, 2, rd, 0x33)
SLTU  = lambda rd, rs1, rs2:       _r(0x00, rs2, rs1, 3, rd, 0x33)
XOR   = lambda rd, rs1, rs2:       _r(0x00, rs2, rs1, 4, rd, 0x33)
SRL   = lambda rd, rs1, rs2:       _r(0x00, rs2, rs1, 5, rd, 0x33)
SRA   = lambda rd, rs1, rs2:       _r(0x20, rs2, rs1, 5, rd, 0x33)
OR    = lambda rd, rs1, rs2:       _r(0x00, rs2, rs1, 6, rd, 0x33)
AND   = lambda rd, rs1, rs2:       _r(0x00, rs2, rs1, 7, rd, 0x33)


# --------------------------------------------------------------- golden ISS

class GoldenRV32I:
    """Reference interpreter for the 37-instruction RV32-WUJI subset."""

    def __init__(self, mem, pc=0):
        self.mem = dict(mem)          # word address -> 32-bit word
        self.pc  = pc & M32
        self.x   = [0] * 32

    # word-level memory helpers (little-endian)
    def _rdw(self, waddr):
        return self.mem.get(waddr & (M32 >> 2), 0)

    def _wrw(self, waddr, data, sel):
        waddr &= M32 >> 2
        old = self.mem.get(waddr, 0)
        mask = 0
        for i in range(4):
            if sel & (1 << i):
                mask |= 0xFF << (8 * i)
        self.mem[waddr] = (old & ~mask) | (data & mask)

    def _wr(self, rd, val):
        if rd:
            self.x[rd] = val & M32

    def step(self):
        insn = self._rdw(self.pc >> 2)
        pc, x = self.pc, self.x
        op  = insn & 0x7F
        rd  = (insn >> 7)  & 0x1F
        f3  = (insn >> 12) & 0x7
        rs1 = (insn >> 15) & 0x1F
        rs2 = (insn >> 20) & 0x1F
        f7  = insn >> 25
        imm_i = _s(insn >> 20, 12)
        next_pc = (pc + 4) & M32

        if op == 0x37:                                    # LUI
            self._wr(rd, insn & 0xFFFFF000)
        elif op == 0x17:                                  # AUIPC
            self._wr(rd, pc + (insn & 0xFFFFF000))
        elif op == 0x6F:                                  # JAL
            imm = _s((((insn >> 31) & 1) << 20) | (((insn >> 12) & 0xFF) << 12)
                     | (((insn >> 20) & 1) << 11) | (((insn >> 21) & 0x3FF) << 1), 21)
            self._wr(rd, pc + 4)
            next_pc = (pc + imm) & M32
        elif op == 0x67:                                  # JALR
            t = (x[rs1] + imm_i) & M32 & ~1
            self._wr(rd, pc + 4)
            next_pc = t
        elif op == 0x63:                                  # branches
            imm = _s((((insn >> 31) & 1) << 12) | (((insn >> 7) & 1) << 11)
                     | (((insn >> 25) & 0x3F) << 5) | (((insn >> 8) & 0xF) << 1), 13)
            a, b = x[rs1], x[rs2]
            sa, sb = sext32(a), sext32(b)
            taken = {0: a == b, 1: a != b, 4: sa < sb, 5: sa >= sb,
                     6: a < b, 7: a >= b}[f3]
            if taken:
                next_pc = (pc + imm) & M32
        elif op == 0x03:                                  # loads
            addr = (x[rs1] + imm_i) & M32
            word = self._rdw(addr >> 2)
            off = addr & 3
            if f3 == 0:
                v = _s((word >> (8 * off)) & 0xFF, 8) & M32
            elif f3 == 4:
                v = (word >> (8 * off)) & 0xFF
            elif f3 == 1:
                v = _s((word >> (16 * (off >> 1))) & 0xFFFF, 16) & M32
            elif f3 == 5:
                v = (word >> (16 * (off >> 1))) & 0xFFFF
            else:
                v = word
            self._wr(rd, v)
        elif op == 0x23:                                  # stores
            imm = _s(((insn >> 25) << 5) | ((insn >> 7) & 0x1F), 12)
            addr = (x[rs1] + imm) & M32
            off = addr & 3
            if f3 == 0:
                data = (x[rs2] & 0xFF) * 0x01010101
                sel = 1 << off
            elif f3 == 1:
                data = (x[rs2] & 0xFFFF) * 0x00010001
                sel = 0b11 << (off & 2)
            else:
                data, sel = x[rs2], 0b1111
            self._wrw(addr >> 2, data, sel)
        elif op == 0x13:                                  # OP-IMM
            a = x[rs1]
            if f3 == 0:  v = a + imm_i
            elif f3 == 2: v = int(sext32(a) < imm_i)
            elif f3 == 3: v = int(a < (imm_i & M32))
            elif f3 == 4: v = a ^ imm_i
            elif f3 == 6: v = a | imm_i
            elif f3 == 7: v = a & imm_i
            elif f3 == 1: v = a << (rs2 & 0x1F)
            else:        # SRLI / SRAI
                sh = rs2 & 0x1F
                v = sext32(a) >> sh if (insn >> 30) & 1 else a >> sh
            self._wr(rd, v)
        elif op == 0x33:                                  # OP
            a, b = x[rs1], x[rs2]
            if f3 == 0:  v = a - b if f7 == 0x20 else a + b
            elif f3 == 1: v = a << (b & 0x1F)
            elif f3 == 2: v = int(sext32(a) < sext32(b))
            elif f3 == 3: v = int(a < b)
            elif f3 == 4: v = a ^ b
            elif f3 == 5:
                sh = b & 0x1F
                v = sext32(a) >> sh if f7 == 0x20 else a >> sh
            elif f3 == 6: v = a | b
            else:         v = a & b
            self._wr(rd, v)
        else:
            raise ValueError(f"unsupported opcode {op:#x} at pc={pc:#x}")

        self.pc = next_pc
