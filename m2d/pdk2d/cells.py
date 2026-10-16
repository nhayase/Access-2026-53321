"""
2D-semiconductor (MoS2) process design kit for M2D.

Standard cell library, design constraints and delay/power models of the
enhancement/depletion-mode n-type MoS2 technology of RV32-WUJI
(Ao et al., Nature 640, 654 (2025)):

  * 25 logic-unit cell types ("2D_NMOS_lib", Extended Data Fig. 4);
  * measured noise margins of single-stage load logic circuits (Fig. 3b);
    cells with a noise margin below 5% of Vdd are excluded from the PDK;
  * fan-out limited to 4 loads of 10 pF total (Fig. 3d);
  * at most 17 cascaded logic stages between flip-flops, giving a maximum
    path delay of 171 us at Vdd = 4 V (Fig. 3c);
  * static power dominated: 0.431 mW for 5,931 transistors at 1 kHz
    (Extended Data Table 2).

Because only n-type MoS2 transistors are available, every cell is built from
a driver network plus a single depletion-load transistor; transistor counts
below follow that series/parallel construction (driver literals + 2 T per
inverted input bubble + 1 load).  DFFHQ is calibrated against the paper:
an 8-bit register uses 144 transistors, i.e. 18 T per flip-flop
(Supplementary Fig. 7).
"""

from dataclasses import dataclass, field


__all__ = [
    "Cell", "LIBRARY", "EXCLUDED_CELLS", "CONSTRAINTS", "PAPER_REFERENCE",
    "CMOS_TRANSISTORS", "cell", "stage_delay_us",
]


# ----------------------------------------------------------------- constraints

@dataclass(frozen=True)
class Constraints:
    vdd:                 float = 4.0     # V   (optimal working voltage)
    min_noise_margin:    float = 0.2     # V   (5% of Vdd exclusion rule)
    max_fanout:          int   = 4       # loads per logic unit (Fig. 3d)
    max_load_pf:         float = 10.0    # pF  total load at max fan-out
    input_cap_pf:        float = 2.5     # pF  per input pin (10 pF / 4)
    max_logic_depth:     int   = 17      # cascaded stages between FFs
    # linear delay model t = t0 + k * C_load.  CALIBRATION, not independent
    # validation: the two coefficients are jointly calibrated so that a
    # 17-stage path at full fan-out reproduces the measured 171 us
    # (17 * (4.06 + 0.6 * 10.0) = 171.0 us); Ao et al. publish the total,
    # not per-stage regression data, so t0 and the slope cannot be fitted
    # independently from the paper alone.  The validation anchors of the
    # flow are therefore the cycle-count checks and the gate-level workload
    # execution (see study.py validation()/gate_level_sim()), not this pair.
    t_intrinsic_us:      float = 4.06
    t_per_pf_us:         float = 0.6
    # static power dominates at kHz operation:
    # 0.431 mW / 5931 transistors = 72.67 nW per transistor
    static_nw_per_t:     float = 0.431e6 / 5931


CONSTRAINTS = Constraints()


def stage_delay_us(fanout, c=CONSTRAINTS):
    """Delay of one logic stage driving `fanout` gate inputs.

    CAVEAT: the load is saturated at `max_fanout` pins, because the paper's
    delay anchor (171 us over 17 stages) is quoted at the maximum legal
    fan-out and the model is not calibrated beyond it.  For netlists that
    HAVE been fan-out legalized (every netlist produced by this flow; zero
    violations by construction) the saturation never binds and the model is
    exact.  For netlists that have NOT been legalized -- in particular the
    yosys+ABC cross-check netlists, which reach fan-out 40 -- the saturation
    makes the reported delay an OPTIMISTIC bound.  ABC delays should
    therefore be read as a lower bound, and the honest mapper-independence
    comparison is the stage COUNT, not the delay.
    """
    load = min(fanout, c.max_fanout) * c.input_cap_pf
    return c.t_intrinsic_us + c.t_per_pf_us * load


# ---------------------------------------------------------------------- cells

@dataclass(frozen=True)
class Cell:
    name:         str
    inputs:       tuple            # ordered pin names
    fn:           object           # python function over the input pins
    transistors:  int
    noise_margin: float = None     # V, where published (Fig. 3b), else None
    seq:          bool  = False    # sequential (flip-flop)
    descr:        str   = ""

    def eval(self, *args):
        return self.fn(*args)


def _lib(*cells):
    return {c.name: c for c in cells}


LIBRARY = _lib(
    # ---- inverters / buffers -------------------------------------------
    Cell("INV",  ("A",), lambda a: ~a, 2, 0.875,
         descr="inverter (enhancement driver + depletion load)"),

    # ---- NAND family ----------------------------------------------------
    Cell("NAND2",  ("A", "B"),      lambda a, b: ~(a & b),        3, 0.605),
    Cell("NAND3",  ("A", "B", "C"), lambda a, b, c: ~(a & b & c), 4, 1.083),
    Cell("NAND2B", ("AN", "B"),     lambda an, b: ~(~an & b),     5, None,
         descr="2-input NOT-AND logic, with 1 inverted input"),
    Cell("NAND3B", ("AN", "B", "C"), lambda an, b, c: ~(~an & b & c), 6, None,
         descr="3-input NOT-AND logic, with 1 inverted input"),

    # ---- NOR family -----------------------------------------------------
    Cell("NOR2",  ("A", "B"),      lambda a, b: ~(a | b),        3, 0.515),
    Cell("NOR3",  ("A", "B", "C"), lambda a, b, c: ~(a | b | c), 4, 0.425),
    Cell("NOR2B", ("AN", "B"),     lambda an, b: ~(~an | b),     5, None,
         descr="2-input NOT-OR logic, with 1 inverted input"),

    # ---- non-inverting --------------------------------------------------
    Cell("AND2", ("A", "B"),      lambda a, b: a & b,        5),
    Cell("AND3", ("A", "B", "C"), lambda a, b, c: a & b & c, 6),
    Cell("OR2",  ("A", "B"),      lambda a, b: a | b,        5),

    # ---- AND-OR-invert --------------------------------------------------
    Cell("AOI21",  ("A0", "A1", "B0"),
         lambda a0, a1, b0: ~((a0 & a1) | b0), 4, 0.584),
    Cell("AOI22",  ("A0", "A1", "B0", "B1"),
         lambda a0, a1, b0, b1: ~((a0 & a1) | (b0 & b1)), 5, 0.754),
    Cell("AOI31",  ("A0", "A1", "A2", "B0"),
         lambda a0, a1, a2, b0: ~((a0 & a1 & a2) | b0), 5, 0.485),
    Cell("AOI32",  ("A0", "A1", "A2", "B0", "B1"),
         lambda a0, a1, a2, b0, b1: ~((a0 & a1 & a2) | (b0 & b1)), 6, 0.435),
    Cell("AOI211", ("A0", "A1", "B0", "C0"),
         lambda a0, a1, b0, c0: ~((a0 & a1) | b0 | c0), 5, 0.613),
    Cell("AOI221", ("A0", "A1", "B0", "B1", "C0"),
         lambda a0, a1, b0, b1, c0: ~((a0 & a1) | (b0 & b1) | c0), 6, 0.487),
    Cell("AOI2BB2", ("A0N", "A1N", "B0", "B1"),
         lambda a0n, a1n, b0, b1: ~((~a0n & ~a1n) | (b0 & b1)), 9, None,
         descr="2-2 AND-OR-inverter logic, with 2 inverted inputs"),

    # ---- OR-AND-invert --------------------------------------------------
    Cell("OAI21", ("A0", "A1", "B0"),
         lambda a0, a1, b0: ~((a0 | a1) & b0), 4, 0.624),
    Cell("OAI22", ("A0", "A1", "B0", "B1"),
         lambda a0, a1, b0, b1: ~((a0 | a1) & (b0 | b1)), 5, 0.542),
    Cell("OAI31", ("A0", "A1", "A2", "B0"),
         lambda a0, a1, a2, b0: ~((a0 | a1 | a2) & b0), 5, 0.412),
    Cell("OAI2BB2", ("A0N", "A1N", "B0", "B1"),
         lambda a0n, a1n, b0, b1: ~((~a0n | ~a1n) & (b0 | b1)), 9, None,
         descr="2-2 OR-AND-inverter logic, with 2 inverted inputs"),

    # ---- complex --------------------------------------------------------
    Cell("XOR2", ("A", "B"), lambda a, b: a ^ b, 9),
    Cell("MUX2", ("A", "B", "S"),
         lambda a, b, s: (a & ~s) | (b & s), 9,
         descr="2-input multiplexer, Y = ~S*A + S*B"),

    # ---- sequential -----------------------------------------------------
    Cell("DFFHQ", ("D", "CLK"), None, 18, None, seq=True,
         descr="positive edge-triggered D flip-flop "
               "(18 T: 8-bit register = 144 T, Supplementary Fig. 7)"),
)


# Cells measured but *excluded* from the PDK because their single-stage-load
# noise margin falls below 5% of Vdd (0.2 V), Fig. 3b (red entries).
EXCLUDED_CELLS = {
    "NOR4":   0.045,
    "NAND4":  0.166,
    "AOI33":  0.184,
    "AOI222": 0.057,
    "OAI33":  0.117,
    "OAI221": 0.094,
    "OAI222": 0.054,
}


# Published figures of RV32-WUJI used as a comparison baseline in reports
# (Extended Data Table 2 and main text).
PAPER_REFERENCE = {
    "transistors":     5931,
    "logic_cells":     None,
    "max_path_delay_us": 171.0,
    "max_logic_depth": 17,
    "max_fanout":      4,
    "operating_hz":    1000.0,
    "power_mw":        0.431,
    "vdd":             4.0,
    # Yield figures of Ao et al. (verified against the main text and the
    # Supplementary Information): 99.92 % functional yield per transistor;
    # inverters: 898 of 900 (99.78 %; reported as 99.77 % in [1],
    # Supplementary Fig. 4); 8-bit shift
    # registers of 144 T at 71 % of 224 and 64-bit registers of 1,152 T at
    # 7 % (2 of the 28 matrices on the wafer of Supplementary Fig. 7).  The
    # per-transistor figure anchors the ladders; tools/block_yield.py fits
    # the negative-binomial (d, alpha) to the two register sizes.
    "transistor_yield": 0.9992,
    "inverter_yield": (898, 900),
    "register_8bit_yield": (159, 224, 144),      # functional, tested, T
    "register_64bit_yield": (2, 28, 1152),
    "channel_um":      (3, 10),      # L, W
}


# --------------------------------------------------- CFET (CMOS) projection
#
# Textbook *static CMOS* transistor counts for the same cell functions,
# used by the design-space study for the "2D CFET + monolithic 3D" scenario
# (Scenario B).  These are NOT measurements: a complementary 2D CFET flow
# does not exist at this maturity today.  Counts follow the standard
# series/parallel pull-up + pull-down construction (2 T per literal,
# + 2 T per inverted input bubble); XOR2/MUX2 assume static (AOI-based)
# implementations, DFFHQ a transmission-gate master-slave flip-flop (24 T).
# The essential physical difference from the E/D-NMOS library is not the
# per-cell count (similar within ~2x) but that complementary logic removes
# the ratioed-load *static current* entirely, leaving leakage only.

CMOS_TRANSISTORS = {
    "INV":     2,
    "NAND2":   4,  "NAND3":  6,  "NAND2B":  6,  "NAND3B":  8,
    "NOR2":    4,  "NOR3":   6,  "NOR2B":   6,
    "AND2":    6,  "AND3":   8,  "OR2":     6,
    "AOI21":   6,  "AOI22":  8,  "AOI31":   8,  "AOI32":  10,
    "AOI211":  8,  "AOI221": 10, "AOI2BB2": 12,
    "OAI21":   6,  "OAI22":  8,  "OAI31":   8,  "OAI2BB2": 12,
    "XOR2":   12,  "MUX2":   12,
    "DFFHQ":  24,
}


def cell(name):
    return LIBRARY[name]
