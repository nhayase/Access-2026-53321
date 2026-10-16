"""Liberty (.lib) writer for the 2D NMOS cell library.

The built-in flow does not need Liberty (the mapper is pure Python), but the
file lets users take the same PDK to native Yosys/ABC, OpenROAD or commercial
tools.  Delay values follow the calibrated linear model of `cells.py`.
"""

from .cells import LIBRARY, CONSTRAINTS, stage_delay_us


__all__ = ["write_liberty"]

_FUNCS = {
    "INV":     "!A",
    "NAND2":   "!(A*B)",
    "NAND3":   "!(A*B*C)",
    "NAND2B":  "!(!AN*B)",
    "NAND3B":  "!(!AN*B*C)",
    "NOR2":    "!(A+B)",
    "NOR3":    "!(A+B+C)",
    "NOR2B":   "!(!AN+B)",
    "AND2":    "(A*B)",
    "AND3":    "(A*B*C)",
    "OR2":     "(A+B)",
    "AOI21":   "!((A0*A1)+B0)",
    "AOI22":   "!((A0*A1)+(B0*B1))",
    "AOI31":   "!((A0*A1*A2)+B0)",
    "AOI32":   "!((A0*A1*A2)+(B0*B1))",
    "AOI211":  "!((A0*A1)+B0+C0)",
    "AOI221":  "!((A0*A1)+(B0*B1)+C0)",
    "AOI2BB2": "!((!A0N*!A1N)+(B0*B1))",
    "OAI21":   "!((A0+A1)*B0)",
    "OAI22":   "!((A0+A1)*(B0+B1))",
    "OAI31":   "!((A0+A1+A2)*B0)",
    "OAI2BB2": "!((!A0N+!A1N)*(B0+B1))",
    "XOR2":    "(A^B)",
    "MUX2":    "((A*!S)+(B*S))",
}


def write_liberty(path, constraints=CONSTRAINTS):
    c = constraints
    d0 = stage_delay_us(1, c)
    d4 = stage_delay_us(c.max_fanout, c)
    out = []
    w = out.append
    w("/* 2D_NMOS_lib -- MoS2 E/D-NMOS standard cells (RV32-WUJI PDK) */")
    w("library(pdk2d_mos2) {")
    w('  delay_model : table_lookup;')
    w('  time_unit : "1us";')
    w("  capacitive_load_unit(1, pf);")
    w(f"  nom_voltage : {c.vdd};")
    w(f"  default_max_fanout : {c.max_fanout};")
    for name, cell in LIBRARY.items():
        w(f"  cell({name}) {{")
        w(f"    area : {cell.transistors};")
        if cell.seq:
            w('    ff(IQ, IQN) { next_state: "D"; clocked_on: "CLK"; }')
            w("    pin(CLK) { direction: input; clock: true; "
              f"capacitance: {c.input_cap_pf}; }}")
            w(f"    pin(D) {{ direction: input; "
              f"capacitance: {c.input_cap_pf}; }}")
            w('    pin(Q) { direction: output; function: "IQ";')
            w('      timing() { related_pin: "CLK"; timing_type: rising_edge;')
            w(f'        cell_rise(scalar) {{ values("{d4:.3f}"); }}')
            w(f'        cell_fall(scalar) {{ values("{d4:.3f}"); }} }} }}')
        else:
            for p in cell.inputs:
                w(f"    pin({p}) {{ direction: input; "
                  f"capacitance: {c.input_cap_pf}; }}")
            w(f'    pin(Y) {{ direction: output; '
              f'function: "{_FUNCS[name]}";')
            w(f"      max_fanout : {c.max_fanout};")
            for p in cell.inputs:
                w(f'      timing() {{ related_pin: "{p}";')
                w(f'        cell_rise(scalar) {{ values("{d0:.3f}"); }}')
                w(f'        cell_fall(scalar) {{ values("{d0:.3f}"); }} }}')
            w("    }")
        w("  }")
    w("}")
    text = "\n".join(out) + "\n"
    with open(path, "w") as f:
        f.write(text)
    return path
