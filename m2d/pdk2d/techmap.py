"""
Pure-Python technology mapping onto the MoS2 standard cell library.

The WASM build of Yosys (yowasp-yosys) cannot invoke ABC, so M2D ships
its own mapper: Yosys first decomposes the design into primitive gates
(`$_AND_`, `$_OR_`, `$_NOT_`, `$_XOR_`, `$_MUX_`, `$_DFF_P_`, ...); this
module then covers the gate network with the 25 cells of the 2D NMOS library
(`m2d.pdk2d.cells`), using a peephole rewriting engine tuned for the
inverting, series/parallel nature of E/D-mode NMOS logic:

  * output-inverter absorption   AND2+INV -> NAND2, OR2+INV -> NOR2, ...
  * input-bubble absorption      INV+NAND2 -> NAND2B, INV feeding MUX2 select
                                 -> input swap, double bubbles -> De Morgan
  * complex-gate covering        AND/OR trees under inverting roots ->
                                 AOI21/22/31/32/211/221/2BB2, OAI21/22/31/2BB2
  * NAND3/NOR3/AND3 chain merging, double-inverter elimination, DCE

Every rewrite strictly decreases the (transistors, cells) pair, so the
process terminates.  Functional correctness is checked by a NumPy bit-parallel
random simulation (`verify_equivalence`): the pre-map primitive netlist and
the mapped netlist are compared on thousands of random patterns at all
primary outputs and all flip-flop D inputs.
"""

import json

import numpy as np

from .cells import LIBRARY


__all__ = ["Netlist", "read_yosys_json", "read_mapped_json", "techmap",
           "verify_equivalence", "legalize_fanout"]


C0, C1 = "c0", "c1"          # constant nets

# combinational library cells grouped by input arity (cheapest first),
# used by the residual-truth-table matcher of the constant propagator
from itertools import permutations
_ASSOC = {"AND2": "AND", "AND3": "AND", "OR2": "OR"}
_COMB_BY_ARITY = {}
for _n, _c in sorted(LIBRARY.items(), key=lambda kv: kv[1].transistors):
    if not _c.seq:
        _COMB_BY_ARITY.setdefault(len(_c.inputs), []).append((_n, _c))
del _n, _c


# ------------------------------------------------------------------ netlist

class Netlist:
    """Single-output-gate netlist.  Gates: gid -> [kind, ins, out, clk]."""

    def __init__(self, name=""):
        self.name    = name
        self.gates   = {}          # gid -> [kind, list(ins), out, clk|None]
        self.inputs  = set()       # primary input nets
        self.outputs = set()       # primary output nets
        self.clocks  = set()       # clock nets (excluded from fan-out rules)
        self._next_gid = 0
        self._next_net = 0

    def new_net(self):
        self._next_net += 1
        return ("n", self._next_net)

    def add(self, kind, ins, out, clk=None):
        gid = self._next_gid
        self._next_gid += 1
        self.gates[gid] = [kind, list(ins), out, clk]
        return gid

    def copy(self):
        nl = Netlist(self.name)
        nl.gates   = {g: [k, list(i), o, c]
                      for g, (k, i, o, c) in self.gates.items()}
        nl.inputs  = set(self.inputs)
        nl.outputs = set(self.outputs)
        nl.clocks  = set(self.clocks)
        nl._next_gid = self._next_gid
        nl._next_net = self._next_net
        return nl

    # ---- derived maps
    def driver_map(self):
        return {g[2]: gid for gid, g in self.gates.items()}

    def consumer_map(self):
        cons = {}
        for gid, (kind, ins, out, clk) in self.gates.items():
            for pos, net in enumerate(ins):
                cons.setdefault(net, set()).add((gid, pos))
        return cons

    def transistors(self):
        return sum(LIBRARY[g[0]].transistors for g in self.gates.values()
                   if g[0] in LIBRARY)

    def counts(self):
        c = {}
        for kind, *_ in self.gates.values():
            c[kind] = c.get(kind, 0) + 1
        return c


# ------------------------------------------------------- yosys JSON reading

# primitive cell pin order: (input pins) -> output pin  [clock pin]
_PRIMS = {
    "$_NOT_":    (("A",), "Y"),
    "$_BUF_":    (("A",), "Y"),
    "$_AND_":    (("A", "B"), "Y"),
    "$_OR_":     (("A", "B"), "Y"),
    "$_XOR_":    (("A", "B"), "Y"),
    "$_XNOR_":   (("A", "B"), "Y"),
    "$_NAND_":   (("A", "B"), "Y"),
    "$_NOR_":    (("A", "B"), "Y"),
    "$_ANDNOT_": (("A", "B"), "Y"),
    "$_ORNOT_":  (("A", "B"), "Y"),
    "$_MUX_":    (("A", "B", "S"), "Y"),
    "$_NMUX_":   (("A", "B", "S"), "Y"),
    "$_AOI3_":   (("A", "B", "C"), "Y"),
    "$_OAI3_":   (("A", "B", "C"), "Y"),
    "$_AOI4_":   (("A", "B", "C", "D"), "Y"),
    "$_OAI4_":   (("A", "B", "C", "D"), "Y"),
}

# primitive boolean functions (bitwise, NumPy compatible)
PRIM_FN = {
    "$_NOT_":    lambda a: ~a,
    "$_BUF_":    lambda a: a,
    "$_AND_":    lambda a, b: a & b,
    "$_OR_":     lambda a, b: a | b,
    "$_XOR_":    lambda a, b: a ^ b,
    "$_XNOR_":   lambda a, b: ~(a ^ b),
    "$_NAND_":   lambda a, b: ~(a & b),
    "$_NOR_":    lambda a, b: ~(a | b),
    "$_ANDNOT_": lambda a, b: a & ~b,
    "$_ORNOT_":  lambda a, b: a | ~b,
    "$_MUX_":    lambda a, b, s: (a & ~s) | (b & s),
    "$_NMUX_":   lambda a, b, s: ~((a & ~s) | (b & s)),
    "$_AOI3_":   lambda a, b, c: ~((a & b) | c),
    "$_OAI3_":   lambda a, b, c: ~((a | b) & c),
    "$_AOI4_":   lambda a, b, c, d: ~((a & b) | (c & d)),
    "$_OAI4_":   lambda a, b, c, d: ~((a | b) & (c | d)),
}


def _bit(v):
    if isinstance(v, int):
        return v
    if v == "0":
        return C0
    if v == "1":
        return C1
    if v == "x":                       # don't-care: tie low
        return C0
    raise ValueError(f"unexpected net bit {v!r}")


def read_yosys_json(path, top=None):
    """Read a gate-level Yosys JSON netlist into a Netlist."""
    with open(path) as f:
        data = json.load(f)
    mods = data["modules"]
    if top is None:
        cands = [n for n, m in mods.items()
                 if m.get("attributes", {}).get("top")] or list(mods)
        top = cands[0]
    mod = mods[top]

    nl = Netlist(top)
    for pname, port in mod["ports"].items():
        for b in port["bits"]:
            net = _bit(b)
            if port["direction"] == "input":
                nl.inputs.add(net)
            else:
                nl.outputs.add(net)

    max_net = 1
    for cname, cell in mod["cells"].items():
        typ = cell["type"]
        conns = cell["connections"]
        for pins in conns.values():
            for b in pins:
                if isinstance(b, int):
                    max_net = max(max_net, b)
        if typ == "$_DFF_P_":
            nl.add("$_DFF_P_", [_bit(conns["D"][0])], _bit(conns["Q"][0]),
                   clk=_bit(conns["C"][0]))
            nl.clocks.add(_bit(conns["C"][0]))
        elif typ in _PRIMS:
            ipins, opin = _PRIMS[typ]
            nl.add(typ, [_bit(conns[p][0]) for p in ipins],
                   _bit(conns[opin][0]))
        else:
            raise ValueError(f"unmapped yosys cell type {typ} ({cname}); "
                             f"extend the gate-level script or _PRIMS")
    nl._next_net = max_net + 1
    return nl


def _parse_net(tok):
    """Inverse of str(net) as written by SynthesisFlow: yosys bit numbers
    are ints, mapper-created nets are ('n', k) tuples, c0/c1 are rails."""
    if tok in (C0, C1):
        return tok
    if tok.isdigit():
        return int(tok)
    if tok.startswith("('n', ") and tok.endswith(")"):
        return ("n", int(tok[6:-1]))
    raise ValueError(f"unrecognized net token {tok!r}")


def read_mapped_json(path):
    """Read a mapped netlist written by SynthesisFlow (build/*_mapped.json)
    back into a Netlist; the clock net is recovered from the flip-flops."""
    with open(path) as f:
        data = json.load(f)
    nl = Netlist(data["name"])
    max_n = 0
    for c in data["cells"]:
        ins = [_parse_net(x) for x in c["ins"]]
        out = _parse_net(c["out"])
        clk = _parse_net(c["clk"]) if "clk" in c else None
        if c["kind"] in ("DFFHQ", "$_DFF_P_"):
            nl.clocks.add(clk)
        nl.add(c["kind"], ins, out, clk)
        for x in ins + [out]:
            if isinstance(x, tuple):
                max_n = max(max_n, x[1])
    nl.inputs = {_parse_net(x) for x in data["inputs"]}
    nl.outputs = {_parse_net(x) for x in data["outputs"]}
    nl._next_net = max_n + 1
    return nl


# ------------------------------------------------------------ direct mapping

def _direct_map(gnet):
    """Translate primitive gates 1:1 (or 1:2) into library cells."""
    nl = Netlist(gnet.name)
    nl.inputs  = set(gnet.inputs)
    nl.outputs = set(gnet.outputs)
    nl.clocks  = set(gnet.clocks)
    nl._next_net = gnet._next_net

    for gid, (kind, ins, out, clk) in gnet.gates.items():
        a = ins
        if kind == "$_DFF_P_":
            nl.add("DFFHQ", [a[0]], out, clk=clk)
        elif kind in ("$_NOT_",):
            nl.add("INV", [a[0]], out)
        elif kind == "$_BUF_":
            t = nl.new_net()
            nl.add("INV", [a[0]], t)
            nl.add("INV", [t], out)
        elif kind == "$_AND_":
            nl.add("AND2", a, out)
        elif kind == "$_OR_":
            nl.add("OR2", a, out)
        elif kind == "$_XOR_":
            nl.add("XOR2", a, out)
        elif kind == "$_XNOR_":
            t = nl.new_net()
            nl.add("XOR2", a, t)
            nl.add("INV", [t], out)
        elif kind == "$_NAND_":
            nl.add("NAND2", a, out)
        elif kind == "$_NOR_":
            nl.add("NOR2", a, out)
        elif kind == "$_ANDNOT_":              # A & ~B
            nl.add("NOR2B", [a[0], a[1]], out)
        elif kind == "$_ORNOT_":               # A | ~B
            nl.add("NAND2B", [a[0], a[1]], out)
        elif kind == "$_MUX_":
            nl.add("MUX2", a, out)
        elif kind == "$_NMUX_":
            t = nl.new_net()
            nl.add("MUX2", a, t)
            nl.add("INV", [t], out)
        elif kind == "$_AOI3_":
            nl.add("AOI21", a, out)
        elif kind == "$_OAI3_":
            nl.add("OAI21", a, out)
        elif kind == "$_AOI4_":
            nl.add("AOI22", a, out)
        elif kind == "$_OAI4_":
            nl.add("OAI22", a, out)
        else:
            raise ValueError(f"cannot map primitive {kind}")
    return nl


# ------------------------------------------------------------------ peephole

class _Rewriter:
    """Peephole engine with incrementally maintained driver/consumer maps."""

    def __init__(self, nl):
        self.nl   = nl
        self.drv  = nl.driver_map()
        self.cons = nl.consumer_map()

    # ---- helpers
    def _fanout(self, net):
        return len(self.cons.get(net, ()))

    def _single(self, net, kinds):
        """Return gate id if `net` is driven by one of `kinds`, feeds exactly
        one gate input and is not a primary output."""
        if net in self.nl.outputs or self._fanout(net) != 1:
            return None
        gid = self.drv.get(net)
        if gid is None:
            return None
        if self.nl.gates[gid][0] in kinds:
            return gid
        return None

    def _delete(self, gid):
        kind, ins, out, clk = self.nl.gates.pop(gid)
        for pos, net in enumerate(ins):
            self.cons[net].discard((gid, pos))
        self.drv.pop(out, None)

    def _replace(self, gid, kind, ins, out):
        self._delete(gid)
        ngid = self.nl.add(kind, ins, out)
        for pos, net in enumerate(ins):
            self.cons.setdefault(net, set()).add((ngid, pos))
        self.drv[out] = ngid
        return ngid

    def _rewire(self, old, new):
        """Route every consumer of net `old` to net `new`."""
        for gid, pos in list(self.cons.get(old, ())):
            self.nl.gates[gid][1][pos] = new
            self.cons[old].discard((gid, pos))
            self.cons.setdefault(new, set()).add((gid, pos))

    def _sole_consumer(self, net):
        (gid, pos), = self.cons[net]
        return gid, pos

    # ---- generic constant-input / duplicate-input simplification -------
    #
    # yosys' opt passes leave a surprising number of gates fed by the
    # constant rails (initialisation muxes from `dfflegalize`, shifter
    # padding, ...).  Instead of one hand-written rule per cell we compute
    # the *residual truth table* of the gate over its distinct non-constant
    # inputs and re-match it against the cheapest library cell (or a plain
    # wire / rail alias).  Run to fixpoint, this is a full constant
    # propagation through the mapped netlist.

    def _alias_out(self, gid, target):
        """Make net `out` of gate `gid` equal to `target` (a net or rail)."""
        kind, ins, out, clk = self.nl.gates[gid]
        if out in self.nl.outputs:
            # primary outputs must keep a driver on their own net
            if target in (C0, C1):
                self._replace(gid, "INV", [C1 if target == C0 else C0], out)
            else:
                mid = self.nl.new_net()
                self._delete(gid)
                g1 = self.nl.add("INV", [target], mid)
                self.cons.setdefault(target, set()).add((g1, 0))
                self.drv[mid] = g1
                g2 = self.nl.add("INV", [mid], out)
                self.cons.setdefault(mid, set()).add((g2, 0))
                self.drv[out] = g2
        else:
            self._delete(gid)
            self._rewire(out, target)
        return True

    def _simplify_gate(self, gid):
        kind, ins, out, clk = self.nl.gates[gid]
        if kind == "DFFHQ":
            return False        # never propagate through state
        # distinct variables, in order of first occurrence
        var = []
        for net in ins:
            if net not in (C0, C1) and net not in var:
                var.append(net)
        if len(var) == len(ins):
            return False        # no constants, no duplicates
        n  = len(var)
        fn = LIBRARY[kind].fn
        tt = []
        for idx in range(1 << n):
            env  = {v: (idx >> i) & 1 for i, v in enumerate(var)}
            args = [1 if net == C1 else 0 if net == C0 else env[net]
                    for net in ins]
            tt.append(fn(*args) & 1)
        # constant output
        if all(b == tt[0] for b in tt):
            return self._alias_out(gid, C1 if tt[0] else C0)
        # wire / inverter of a single variable
        for i, v in enumerate(var):
            if all(tt[idx] == (idx >> i) & 1 for idx in range(1 << n)):
                return self._alias_out(gid, v)
            if all(tt[idx] == 1 - ((idx >> i) & 1) for idx in range(1 << n)):
                self._replace(gid, "INV", [v], out)
                return True
        # re-match against library cells of the reduced arity
        best = None
        for cname, c in _COMB_BY_ARITY.get(n, ()):
            if best is not None and c.transistors >= best[2]:
                continue
            for perm in permutations(range(n)):
                if all(c.fn(*[(idx >> perm[k]) & 1 for k in range(n)]) & 1
                       == tt[idx] for idx in range(1 << n)):
                    best = (cname, perm, c.transistors)
                    break
        if best is not None and (best[0] != kind or len(ins) != n):
            cname, perm, _t = best
            self._replace(gid, cname, [var[p] for p in perm], out)
            return True
        return False

    # ---- associative tree rebalancing ----------------------------------
    #
    # Without ABC, yosys leaves left-associative RTL expressions such as
    # `t0 | t1 | ... | t6` as *linear* OR2 chains (depth n-1).  This pass
    # collects maximal fanout-1 AND/OR trees and rebuilds them as balanced
    # binary trees (depth ceil(log2 n)); the peephole rules then re-absorb
    # pairs into AND3/AOI/OAI cells.  Rebuilds only when the depth strictly
    # improves, so interleaving with the peephole fixpoint terminates.

    def _is_internal(self, net, base):
        if net in self.nl.outputs or self._fanout(net) != 1:
            return False
        gid = self.drv.get(net)
        return gid is not None and _ASSOC.get(self.nl.gates[gid][0]) == base

    def balance_pass(self):
        changed = False
        for gid in list(self.nl.gates):
            if gid not in self.nl.gates:
                continue
            kind, ins, out, clk = self.nl.gates[gid]
            base = _ASSOC.get(kind)
            if base is None:
                continue
            # skip non-roots: gates that are themselves folded into a larger
            # same-base tree (single consumer of the same base function)
            if out not in self.nl.outputs and self._fanout(out) == 1:
                cg, _pos = self._sole_consumer(out)
                if _ASSOC.get(self.nl.gates[cg][0]) == base:
                    continue
            leaves, maxd = [], [0]

            def collect(net, d):
                if self._is_internal(net, base):
                    for sub in self.nl.gates[self.drv[net]][1]:
                        collect(sub, d + 1)
                else:
                    leaves.append(net)
                    maxd[0] = max(maxd[0], d)
            for net in ins:
                collect(net, 1)
            uniq = list(dict.fromkeys(leaves))   # AND/OR are idempotent
            newd = max(1, (len(uniq) - 1).bit_length())
            if newd >= maxd[0]:
                continue
            k2 = "AND2" if base == "AND" else "OR2"
            if len(uniq) == 1:
                self._alias_out(gid, uniq[0])
            else:
                level = uniq
                while len(level) > 2:
                    nxt = []
                    for i in range(0, len(level) - 1, 2):
                        t = self.nl.new_net()
                        g = self.nl.add(k2, [level[i], level[i + 1]], t)
                        self.cons.setdefault(level[i],     set()).add((g, 0))
                        self.cons.setdefault(level[i + 1], set()).add((g, 1))
                        self.drv[t] = g
                        nxt.append(t)
                    if len(level) % 2:
                        nxt.append(level[-1])
                    level = nxt
                self._replace(gid, k2, level, out)
            changed = True
        return changed

    # ---- one full pass; returns True if anything changed
    def run_pass(self):
        changed = False
        for gid in list(self.nl.gates):
            if gid not in self.nl.gates:
                continue
            if self._try_gate(gid):
                changed = True
        return changed

    def _try_gate(self, gid):
        # constant / duplicate-input folding first: it exposes further
        # peephole opportunities and vice versa (fixpoint over both).
        if self._simplify_gate(gid):
            return True
        kind, ins, out, clk = self.nl.gates[gid]

        # ---- double-inverter elimination -------------------------------
        if kind == "INV":
            src = self._single(ins[0], ("INV",))
            if src is not None and out not in self.nl.outputs:
                y = self.nl.gates[src][1][0]
                self._rewire(out, y)
                self._delete(gid)
                self._delete(src)
                return True

        # ---- chain merging ---------------------------------------------
        if kind == "AND2":
            for i in (0, 1):
                src = self._single(ins[i], ("AND2",))
                if src is not None:
                    sub = self.nl.gates[src][1]
                    self._replace(gid, "AND3", sub + [ins[1 - i]], out)
                    self._delete(src)
                    return True
        if kind == "NAND2":
            for i in (0, 1):
                src = self._single(ins[i], ("AND2",))
                if src is not None:
                    sub = self.nl.gates[src][1]
                    self._replace(gid, "NAND3", sub + [ins[1 - i]], out)
                    self._delete(src)
                    return True
        if kind == "NOR2":
            for i in (0, 1):
                src = self._single(ins[i], ("OR2",))
                if src is not None:
                    sub = self.nl.gates[src][1]
                    self._replace(gid, "NOR3", sub + [ins[1 - i]], out)
                    self._delete(src)
                    return True

        # ---- AOI covering (inverting root over AND arms) ---------------
        if kind == "NOR2":
            arm = [self._single(n, ("AND2",)) for n in ins]
            a3  = [self._single(n, ("AND3",)) for n in ins]
            nr  = [self._single(n, ("NOR2",)) for n in ins]
            if arm[0] is not None and arm[1] is not None:      # AOI22
                i0 = self.nl.gates[arm[0]][1]
                i1 = self.nl.gates[arm[1]][1]
                self._replace(gid, "AOI22", i0 + i1, out)
                self._delete(arm[0]); self._delete(arm[1])
                return True
            for i in (0, 1):
                if a3[i] is not None and arm[1 - i] is not None:  # AOI32
                    ia = self.nl.gates[a3[i]][1]
                    ib = self.nl.gates[arm[1 - i]][1]
                    self._replace(gid, "AOI32", ia + ib, out)
                    self._delete(a3[i]); self._delete(arm[1 - i])
                    return True
            for i in (0, 1):
                if a3[i] is not None:                             # AOI31
                    ia = self.nl.gates[a3[i]][1]
                    self._replace(gid, "AOI31", ia + [ins[1 - i]], out)
                    self._delete(a3[i])
                    return True
            for i in (0, 1):
                if nr[i] is not None and arm[1 - i] is not None:  # AOI2BB2
                    ia = self.nl.gates[nr[i]][1]        # ~a & ~b
                    ib = self.nl.gates[arm[1 - i]][1]
                    self._replace(gid, "AOI2BB2", ia + ib, out)
                    self._delete(nr[i]); self._delete(arm[1 - i])
                    return True
            for i in (0, 1):
                if arm[i] is not None:                            # AOI21
                    ia = self.nl.gates[arm[i]][1]
                    self._replace(gid, "AOI21", ia + [ins[1 - i]], out)
                    self._delete(arm[i])
                    return True
        if kind == "NOR3":
            arm = [self._single(n, ("AND2",)) for n in ins]
            hits = [i for i, s in enumerate(arm) if s is not None]
            if len(hits) >= 2:                                    # AOI221
                i0, i1 = hits[0], hits[1]
                rest = [ins[j] for j in range(3) if j not in (i0, i1)]
                ia = self.nl.gates[arm[i0]][1]
                ib = self.nl.gates[arm[i1]][1]
                self._replace(gid, "AOI221", ia + ib + rest, out)
                self._delete(arm[i0]); self._delete(arm[i1])
                return True
            if len(hits) == 1:                                    # AOI211
                i0 = hits[0]
                rest = [ins[j] for j in range(3) if j != i0]
                ia = self.nl.gates[arm[i0]][1]
                self._replace(gid, "AOI211", ia + rest, out)
                self._delete(arm[i0])
                return True

        # ---- OAI covering (inverting root over OR arms) ----------------
        if kind == "NAND2":
            arm = [self._single(n, ("OR2",)) for n in ins]
            nd  = [self._single(n, ("NAND2",)) for n in ins]
            # OAI31: ~((a|b|c) & d) via nested OR2
            for i in (0, 1):
                if arm[i] is not None:
                    o = self.nl.gates[arm[i]][1]
                    for j in (0, 1):
                        src = self._single(o[j], ("OR2",))
                        if src is not None:
                            sub = self.nl.gates[src][1]
                            self._replace(gid, "OAI31",
                                          sub + [o[1 - j], ins[1 - i]], out)
                            self._delete(arm[i]); self._delete(src)
                            return True
            if arm[0] is not None and arm[1] is not None:         # OAI22
                i0 = self.nl.gates[arm[0]][1]
                i1 = self.nl.gates[arm[1]][1]
                self._replace(gid, "OAI22", i0 + i1, out)
                self._delete(arm[0]); self._delete(arm[1])
                return True
            for i in (0, 1):
                if nd[i] is not None and arm[1 - i] is not None:  # OAI2BB2
                    ia = self.nl.gates[nd[i]][1]        # ~a | ~b
                    ib = self.nl.gates[arm[1 - i]][1]
                    self._replace(gid, "OAI2BB2", ia + ib, out)
                    self._delete(nd[i]); self._delete(arm[1 - i])
                    return True
            for i in (0, 1):
                if arm[i] is not None:                            # OAI21
                    ia = self.nl.gates[arm[i]][1]
                    self._replace(gid, "OAI21", ia + [ins[1 - i]], out)
                    self._delete(arm[i])
                    return True

        # ---- output-inverter absorption --------------------------------
        _OUT_FOLD = {"AND2": "NAND2", "OR2": "NOR2", "AND3": "NAND3",
                     "NAND2": "AND2", "NOR2": "OR2", "NAND3": "AND3"}
        if kind in _OUT_FOLD and out not in self.nl.outputs \
                and self._fanout(out) == 1:
            cgid, _ = self._sole_consumer(out)
            ck, cins, cout, _ = self.nl.gates[cgid]
            if ck == "INV":
                # only fold if it does not increase transistors
                gain = (LIBRARY[kind].transistors + LIBRARY["INV"].transistors
                        - LIBRARY[_OUT_FOLD[kind]].transistors)
                if gain >= 0:
                    self._delete(cgid)
                    self._replace(gid, _OUT_FOLD[kind], ins, cout)
                    return True

        # ---- input-bubble absorption -----------------------------------
        def inv_src(net):
            return self._single(net, ("INV",))

        if kind == "NAND2":
            s0, s1 = inv_src(ins[0]), inv_src(ins[1])
            if s0 is not None and s1 is not None:      # De Morgan -> OR2
                y0 = self.nl.gates[s0][1][0]
                y1 = self.nl.gates[s1][1][0]
                self._replace(gid, "OR2", [y0, y1], out)
                self._delete(s0); self._delete(s1)
                return True
            for i, s in ((0, s0), (1, s1)):
                if s is not None:                      # NAND2B(AN, B)
                    y = self.nl.gates[s][1][0]
                    self._replace(gid, "NAND2B", [y, ins[1 - i]], out)
                    self._delete(s)
                    return True
        if kind == "NOR2":
            s0, s1 = inv_src(ins[0]), inv_src(ins[1])
            if s0 is not None and s1 is not None:      # De Morgan -> AND2
                y0 = self.nl.gates[s0][1][0]
                y1 = self.nl.gates[s1][1][0]
                self._replace(gid, "AND2", [y0, y1], out)
                self._delete(s0); self._delete(s1)
                return True
            for i, s in ((0, s0), (1, s1)):
                if s is not None:                      # NOR2B(AN, B)
                    y = self.nl.gates[s][1][0]
                    self._replace(gid, "NOR2B", [y, ins[1 - i]], out)
                    self._delete(s)
                    return True
        if kind == "AND2":                             # a & ~y -> NOR2B(a, y)
            for i in (0, 1):
                s = inv_src(ins[i])
                if s is not None:
                    y = self.nl.gates[s][1][0]
                    self._replace(gid, "NOR2B", [ins[1 - i], y], out)
                    self._delete(s)
                    return True
        if kind == "OR2":                              # a | ~y -> NAND2B(a, y)
            for i in (0, 1):
                s = inv_src(ins[i])
                if s is not None:
                    y = self.nl.gates[s][1][0]
                    self._replace(gid, "NAND2B", [ins[1 - i], y], out)
                    self._delete(s)
                    return True
        if kind == "NAND3":
            for i in range(3):
                s = inv_src(ins[i])
                if s is not None:
                    y = self.nl.gates[s][1][0]
                    rest = [ins[j] for j in range(3) if j != i]
                    self._replace(gid, "NAND3B", [y] + rest, out)
                    self._delete(s)
                    return True
        if kind == "MUX2":                             # inverted select: swap
            s = inv_src(ins[2])
            if s is not None:
                y = self.nl.gates[s][1][0]
                self._replace(gid, "MUX2", [ins[1], ins[0], y], out)
                self._delete(s)
                return True
        if kind == "AOI22":
            for base in (0, 2):
                s0, s1 = inv_src(ins[base]), inv_src(ins[base + 1])
                if s0 is not None and s1 is not None:  # -> AOI2BB2
                    y0 = self.nl.gates[s0][1][0]
                    y1 = self.nl.gates[s1][1][0]
                    other = [ins[j] for j in range(4)
                             if j not in (base, base + 1)]
                    self._replace(gid, "AOI2BB2", [y0, y1] + other, out)
                    self._delete(s0); self._delete(s1)
                    return True
        if kind == "OAI22":
            for base in (0, 2):
                s0, s1 = inv_src(ins[base]), inv_src(ins[base + 1])
                if s0 is not None and s1 is not None:  # -> OAI2BB2
                    y0 = self.nl.gates[s0][1][0]
                    y1 = self.nl.gates[s1][1][0]
                    other = [ins[j] for j in range(4)
                             if j not in (base, base + 1)]
                    self._replace(gid, "OAI2BB2", [y0, y1] + other, out)
                    self._delete(s0); self._delete(s1)
                    return True
        return False

    def dce(self):
        """Remove gates whose output is unused."""
        removed = False
        again = True
        while again:
            again = False
            for gid in list(self.nl.gates):
                kind, ins, out, clk = self.nl.gates[gid]
                if kind == "DFFHQ":
                    continue
                if out not in self.nl.outputs and self._fanout(out) == 0:
                    self._delete(gid)
                    removed = again = True
        return removed


def techmap(gnet, max_passes=64):
    """Map a primitive gate netlist to the MoS2 library and optimize."""
    nl = _direct_map(gnet)
    rw = _Rewriter(nl)
    rw.dce()
    for _ in range(max_passes):
        changed = rw.run_pass()
        changed |= rw.dce()
        if not changed:
            break
    # depth optimization: rebalance associative chains, then let the
    # peephole rules re-cover the balanced trees; repeat to fixpoint
    for _ in range(8):
        if not rw.balance_pass():
            break
        rw.dce()
        for _ in range(max_passes):
            if not (rw.run_pass() | rw.dce()):
                break
    return nl


# --------------------------------------------------------------- fanout fix

def legalize_fanout(nl, max_fanout=4):
    """Insert inverter buffer trees so no cell output drives more than
    `max_fanout` internal gate inputs (clock pins excluded: RV32-WUJI is
    driven by an external clock).

    The tree uses an *even number of inverter levels* with alternating
    polarity instead of chained INV pairs: with L levels the tree serves up
    to max_fanout**(L+1) sinks at a depth penalty of only L stages
    (L = 2 covers 64 sinks), whereas a pair-based tree pays 2 stages per
    recursion level.  Returns the number of inverters inserted."""
    inserted = 0
    cons = nl.consumer_map()

    def data_sinks(net):
        return [(gid, pos) for (gid, pos) in cons.get(net, ())
                if not (nl.gates[gid][0] == "DFFHQ" and pos > 0)]

    work = [g[2] for g in list(nl.gates.values())] + list(nl.inputs)
    for net in work:
        if net in nl.clocks or net in (C0, C1):   # power rails: no buffering
            continue
        sinks = data_sinks(net)
        if len(sinks) <= max_fanout:
            continue

        # smallest even level count L with capacity >= number of sinks
        levels = 2
        while max_fanout ** (levels + 1) < len(sinks):
            levels += 2

        # build bottom-up: group sinks under level-L inverters, then group
        # those inverters under level-(L-1) inverters, ... level-1 inverters
        # hang off the original net.
        layer = sinks                       # list of (gid, pos) input pins
        for lvl in range(levels, 0, -1):
            groups = [layer[i:i + max_fanout]
                      for i in range(0, len(layer), max_fanout)]
            nxt = []
            for grp in groups:
                t = nl.new_net()
                g = nl.add("INV", [nl.new_net()], t)   # input patched below
                inserted += 1
                cons.setdefault(t, set())
                for gid, pos in grp:
                    nl.gates[gid][1][pos] = t
                    cons[t].add((gid, pos))
                nxt.append((g, 0))
            layer = nxt
        # connect the level-1 inverters to the source net
        for gid, pos in sinks:
            cons[net].discard((gid, pos))
        for gid, pos in layer:
            nl.gates[gid][1][pos] = net
            cons[net].add((gid, pos))
        assert len(layer) <= max_fanout
    return inserted


# ---------------------------------------------------- equivalence checking

def _topo_order(nl):
    """Topological order of combinational gates (DFF outputs are sources)."""
    drv = nl.driver_map()
    indeg = {}
    dep = {}
    for gid, (kind, ins, out, clk) in nl.gates.items():
        if kind in ("DFFHQ", "$_DFF_P_"):
            continue
        n = 0
        for net in ins:
            d = drv.get(net)
            if d is not None and nl.gates[d][0] not in ("DFFHQ", "$_DFF_P_"):
                dep.setdefault(d, []).append(gid)
                n += 1
        indeg[gid] = n
    order = [g for g, n in indeg.items() if n == 0]
    head = 0
    while head < len(order):
        g = order[head]; head += 1
        for h in dep.get(g, ()):
            indeg[h] -= 1
            if indeg[h] == 0:
                order.append(h)
    if len(order) != len(indeg):
        raise RuntimeError("combinational loop detected")
    return order


def _simulate(nl, pi_vals, words):
    """NumPy bit-parallel evaluation; returns {net: uint64 array}."""
    vals = dict(pi_vals)
    vals[C0] = np.zeros(words, dtype=np.uint64)
    vals[C1] = ~np.zeros(words, dtype=np.uint64)
    fns = dict(PRIM_FN)
    for name, c in LIBRARY.items():
        if not c.seq:
            fns[name] = c.fn
    for gid in _topo_order(nl):
        kind, ins, out, clk = nl.gates[gid]
        vals[out] = fns[kind](*(vals[n] for n in ins))
    return vals


def verify_equivalence(gnet, mapped, patterns=8192, seed=0x2D5EED):
    """Compare the primitive netlist and the mapped netlist on random input
    patterns at every primary output and every flip-flop D input.

    Flip-flop outputs (state bits) are driven as free pseudo-inputs, making
    this a combinational check of the full next-state and output functions.
    Raises AssertionError on mismatch; returns the number of patterns."""
    words = (patterns + 63) // 64
    rng = np.random.default_rng(seed)

    def ff_gids(nl):
        return sorted(g for g, (k, *_r) in nl.gates.items()
                      if k in ("DFFHQ", "$_DFF_P_"))

    ga, gb = ff_gids(gnet), ff_gids(mapped)
    if len(ga) != len(gb):
        raise AssertionError(
            f"flip-flop count changed during mapping: {len(ga)} != {len(gb)}")

    pis = {}
    for net in gnet.inputs:
        if net in (C0, C1):
            continue
        pis[net] = rng.integers(0, 1 << 64, size=words, dtype=np.uint64)
    # state bits: identical Q nets exist in both netlists
    for gid in ga:
        q = gnet.gates[gid][2]
        pis[q] = rng.integers(0, 1 << 64, size=words, dtype=np.uint64)

    va = _simulate(gnet,  pis, words)
    vb = _simulate(mapped, pis, words)

    for net in sorted(gnet.outputs, key=str):
        if not np.array_equal(va.get(net, pis.get(net)),
                              vb.get(net, pis.get(net))):
            raise AssertionError(f"mismatch at primary output net {net}")
    for gid_a, gid_b in zip(ga, gb):
        da = gnet.gates[gid_a][1][0]
        db = mapped.gates[gid_b][1][0]
        if not np.array_equal(va.get(da, pis.get(da)),
                              vb.get(db, pis.get(db))):
            raise AssertionError(f"mismatch at flip-flop D input (Q net "
                                 f"{gnet.gates[gid_a][2]})")
    return words * 64
