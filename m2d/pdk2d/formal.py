"""
Formal equivalence checking of the synthesis flow (SAT-based).

Three proofs replace the random-pattern checks as the evidence for the flow:

  prove_comb_equivalent(a, b)
      Combinational equivalence of two netlists with the same flip-flops:
      every primary output and every flip-flop D input of `a` equals the
      corresponding one of `b` for ALL values of the primary inputs and of
      the flip-flop outputs (the full next-state and output functions).
      Used for primitive -> mapped (technology mapping) and mapped ->
      fan-out-legalized netlist.

  prove_subcycle(mapped, pres, ports)
      One architectural cycle of the depth-compliant physical netlist
      (`pipeline.subcycle_pipeline`) against one evaluation of the mapped
      netlist, for ALL architectural states, ALL pipeline-register contents,
      ALL primary-input values and ALL environment garbage: the ring starts
      in phase 0 (as at every architectural boundary), rst = 0, the
      environment is the two-phase sub-cycle responder of `verify_subcycle`
      with a fresh free garbage value per input, period and phase.  The
      architectural state after the S-th edge and the primary outputs of the
      last period must equal the mapped netlist's.  Because every
      architectural cycle starts from phase 0 with arbitrary pipeline
      contents, the one-cycle proof holds for every cycle by induction.

Method: both sides are built into one and-inverter graph with structural
hashing and constant folding (cell functions are evaluated symbolically on
AIG literals, so a library cell and the primitive gates it replaces collapse
to the same node wherever the structure agrees); every output pair whose
literals still differ is proved by CaDiCaL on the Tseitin encoding of their
cones.  A satisfiable miter raises AssertionError with the output name.
"""

from .cells import LIBRARY
from .techmap import C0, C1, PRIM_FN, _topo_order


__all__ = ["AIG", "prove_comb_equivalent", "prove_subcycle"]

_SEQ = ("DFFHQ", "$_DFF_P_")


class AIG:
    """Literals: 0 = false, 1 = true, 2v / 2v+1 = variable v / its negation."""

    def __init__(self):
        self.nvars = 0
        self.ands = {}            # var -> (lit_a, lit_b)
        self.strash = {}

    def var(self):
        self.nvars += 1
        return 2 * self.nvars

    def AND(self, a, b):
        if a == 0 or b == 0 or a == (b ^ 1):
            return 0
        if a == 1:
            return b
        if b == 1 or a == b:
            return a
        if a > b:
            a, b = b, a
        key = (a, b)
        v = self.strash.get(key)
        if v is None:
            v = self.var()
            self.ands[v >> 1] = key
            self.strash[key] = v
        return v

    def OR(self, a, b):
        return self.AND(a ^ 1, b ^ 1) ^ 1

    def XOR(self, a, b):
        return self.OR(self.AND(a, b ^ 1), self.AND(a ^ 1, b))

    def MUX(self, s, a, b):          # s ? b : a
        return self.OR(self.AND(s ^ 1, a), self.AND(s, b))


class _L:
    """AIG literal with Python bit operators, so the cell lambdas of
    `cells.LIBRARY` and `techmap.PRIM_FN` evaluate symbolically."""
    __slots__ = ("g", "l")

    def __init__(self, g, l):
        self.g, self.l = g, l

    def __and__(self, o):
        return _L(self.g, self.g.AND(self.l, o.l))

    def __or__(self, o):
        return _L(self.g, self.g.OR(self.l, o.l))

    def __xor__(self, o):
        return _L(self.g, self.g.XOR(self.l, o.l))

    def __invert__(self):
        return _L(self.g, self.l ^ 1)


def _fns():
    fns = dict(PRIM_FN)
    for name, c in LIBRARY.items():
        if not c.seq:
            fns[name] = c.fn
    return fns


def _eval(g, nl, order, fns, vals):
    """Evaluate the combinational gates of `nl` into `vals` (net -> lit)."""
    for gid in order:
        kind, ins, out, _clk = nl.gates[gid]
        vals[out] = fns[kind](*(_L(g, vals[n]) for n in ins)).l


def _ffs(nl):
    return sorted(g for g, (k, *_r) in nl.gates.items() if k in _SEQ)


class _Prover:
    """Proves lit pairs equal on the Tseitin encoding of their cones."""

    def __init__(self, g):
        from pysat.solvers import Solver
        self.g = g
        self.s = Solver(name="cadical153")
        self.done = set()
        self.calls = 0
        self.s.add_clause([1])          # solver var 1 is the constant true

    def _cl(self, lit):
        # AIG var v is solver var v + 1; solver var 1 is the constant
        if lit < 2:
            return 1 if lit == 1 else -1
        v = (lit >> 1) + 1
        return -v if lit & 1 else v

    def equal(self, a, b):
        if a == b:
            return True
        self.calls += 1
        self._encode_shift(a)
        self._encode_shift(b)
        la, lb = self._cl(a), self._cl(b)
        # a != b  satisfiable?  (two calls: a & ~b, ~a & b)
        for asm in ([la, -lb], [-la, lb]):
            if self.s.solve(assumptions=asm):
                return False
        return True

    def _encode_shift(self, lit):
        stack = [lit >> 1]
        while stack:
            v = stack.pop()
            if v in self.done or v not in self.g.ands:
                continue
            self.done.add(v)
            a, b = self.g.ands[v]
            x, y, z = v + 1, self._cl(a), self._cl(b)
            self.s.add_clause([-x, y])
            self.s.add_clause([-x, z])
            self.s.add_clause([x, -y, -z])
            stack.extend((a >> 1, b >> 1))


def prove_comb_equivalent(a, b):
    """Formal combinational equivalence of netlists `a` and `b` (same
    primary inputs/outputs; flip-flops matched in gid order and sharing
    their Q nets).  Returns a dict of statistics; raises AssertionError
    naming the first differing output."""
    g = AIG()
    fns = _fns()
    fa, fb = _ffs(a), _ffs(b)
    if len(fa) != len(fb):
        raise AssertionError(f"flip-flop count differs: {len(fa)} != {len(fb)}")
    src = {C0: 0, C1: 1}
    for net in a.inputs | b.inputs:
        if net not in (C0, C1):
            src.setdefault(net, g.var())
    for gid in fa:
        src[a.gates[gid][2]] = g.var()
    for ga_, gb_ in zip(fa, fb):
        if a.gates[ga_][2] != b.gates[gb_][2]:
            raise AssertionError("flip-flop Q nets do not correspond")
    va, vb = dict(src), dict(src)
    _eval(g, a, _topo_order(a), fns, va)
    _eval(g, b, _topo_order(b), fns, vb)
    pairs = [(f"PO {n}", va[n], vb[n]) for n in sorted(a.outputs, key=str)
             if n not in (C0, C1)]
    pairs += [(f"D of Q {a.gates[x][2]}", va[a.gates[x][1][0]],
               vb[b.gates[y][1][0]]) for x, y in zip(fa, fb)]
    p = _Prover(g)
    hashed = 0
    for name, la, lb in pairs:
        if la == lb:
            hashed += 1
            continue
        if not p.equal(la, lb):
            raise AssertionError(f"not equivalent at {name}")
    return {"outputs": len(pairs), "by_hashing": hashed,
            "by_sat": len(pairs) - hashed, "aig_ands": len(g.ands)}


def prove_subcycle(mapped, pres, ports, env_deps=None):
    """Formal one-architectural-cycle equivalence of the physical netlist
    `pres.netlist` (S periods) and `mapped` (one evaluation); see module
    docstring.  Returns statistics; raises AssertionError on a difference."""
    from .pipeline import ENV_DEPS, _env_dep_map, _pi_nets
    env_deps = ENV_DEPS if env_deps is None else env_deps
    g = AIG()
    fns = _fns()
    nl, S = pres.netlist, pres.subcycles

    # reference: one evaluation of the mapped next-state/output function
    rst = _pi_nets(mapped, ports, "rst")[0]
    pi = {C0: 0, C1: 1}
    for net in mapped.inputs:
        if net in (C0, C1) or net in mapped.clocks:
            continue
        pi[net] = 0 if net == rst else g.var()
    ref = dict(pi)
    arch_q = {mapped.gates[x][2]: g.var() for x in _ffs(mapped)}
    ref.update(arch_q)
    _eval(g, mapped, _topo_order(mapped), fns, ref)
    ref_next = {mapped.gates[x][2]: ref[mapped.gates[x][1][0]]
                for x in _ffs(mapped)}
    po = [b for b in mapped.outputs if b not in (C0, C1)]
    ref_po = {b: ref.get(b, pi.get(b, 0)) for b in po}

    # physical netlist: S periods
    order = _topo_order(nl)
    ffs = _ffs(nl)
    vals = dict(pi)
    ring = set(pres.ring)
    for x in ffs:
        q = nl.gates[x][2]
        if q in arch_q:
            vals[q] = arch_q[q]
        elif q not in ring:
            vals[q] = g.var()            # arbitrary pipeline contents
    for i, q in enumerate(pres.ring):
        vals[q] = 1 if i == 0 else 0
    dep_of = {b: d for b, d in _env_dep_map(mapped, ports, env_deps).items()
              if b != rst and d}
    p = _Prover(g)
    for sub in range(S):
        # phase A: environment inputs are garbage, outputs evaluated
        for b in dep_of:
            vals[b] = g.var()
        _eval(g, nl, order, fns, vals)
        # environment: true value where every dependency already shows its
        # final (reference) value, fresh garbage elsewhere
        for b, deps in dep_of.items():
            ok = 1
            for x in deps:
                got = vals.get(x, pi.get(x, 0))
                ok = g.AND(ok, g.XOR(got, ref_po[x]) ^ 1)
            vals[b] = g.MUX(ok, g.var(), pi[b])
        _eval(g, nl, order, fns, vals)            # phase B
        if sub == S - 1:
            for b, want in ref_po.items():
                got = vals.get(b, pi.get(b, 0))
                if not p.equal(got, want):
                    raise AssertionError(
                        f"primary output {b} differs in period {S - 1}")
        nxt = {nl.gates[x][2]: vals[nl.gates[x][1][0]] for x in ffs}
        vals.update(nxt)
        for i, q in enumerate(pres.ring):
            if vals[q] != (1 if i == (sub + 1) % S else 0):
                raise AssertionError("ring counter is not one-hot")
    hashed = 0
    for q, want in ref_next.items():
        if vals[q] == want:
            hashed += 1
        elif not p.equal(vals[q], want):
            raise AssertionError(f"architectural next state differs at {q}")
    return {"periods": S, "outputs": len(ref_po) + len(ref_next),
            "next_state_by_hashing": hashed, "sat_calls": p.calls,
            "aig_ands": len(g.ands)}
