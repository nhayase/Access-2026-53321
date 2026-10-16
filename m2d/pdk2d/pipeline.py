"""
Sub-cycle pipelining: a depth-compliant (<= 17 stages) *physical* netlist
built from a mapped, fan-out-legalized netlist by inserting real DFFHQ
flip-flops, hold multiplexers and a one-hot ring counter.

Motivation.  RV32-WUJI (Ao et al., Nature 640, 654 (2025)) is built with
at most 17 cascaded logic stages between flip-flops.  If that rule is a
physical limit of E/D-mode NMOS logic (signal-level restoration over long
unclocked cascades) rather than a delay budget, a netlist of depth D > 17
cannot be fabricated in the process at all.  Every design point of the
study has D between 34 and 125.  This module turns each of them into a
netlist in which *every* register-to-register path has at most 17 cells,
using only the cells of 2D_NMOS_lib, and does so as an actual structural
transformation whose result is analyzed by the ordinary DRC/timing flow
(`analyze`), verified for sequential equivalence against the original
netlist (`verify_subcycle`), and executed at gate level on the workloads
(`study.py`, section 10).

Construction (one architectural cycle = S physical clock periods)
----------------------------------------------------------------
1. A one-hot ring counter of S DFFHQ (p[0..S-1]) generates the sub-cycle
   phases; arch_en = p[S-1] | rst.  With rst asserted the ring is forced
   to phase 0 and arch_en is 1 in every period, so the synchronous reset
   of the core takes effect exactly as in the original netlist.
2. Every flip-flop of the original netlist ("architectural" flip-flop)
   receives a hold multiplexer, D' = MUX2(A = Q, B = D, S = arch_en), and
   therefore latches its next state only in the last sub-cycle; the
   architectural state is constant for the S periods.  Where the hold
   input would raise the fan-out of Q above the limit, the least critical
   sink of Q and the hold input are moved behind an INV pair.
   A flip-flop whose next-state net lies in the last sub-cycle band and
   whose output reaches -- through combinational cells -- only endpoints
   of the last band (no primary output, hold-multiplexer data input or
   flip-flop D input of an earlier band) needs no hold multiplexer: its Q
   is the current state in sub-cycle 0, which is exactly when the first
   band reads it, and the registered copies of Q carry that value to the
   later bands; the values it latches at the intermediate edges reach
   nothing that is sampled.  Dropping the multiplexer there removes one
   stage from exactly the endpoints that set S (`_holdless_ok`; the
   choice is re-verified by `verify_subcycle`).
3. Logic levels are assigned with the flip-flop outputs at level 0.  A
   primary input driven by the external environment (memory, register
   file) is assigned the level of the output-port bits it is a function
   of (`ENV_DEPS`): the environment is the same zero-delay combinational
   responder in host (silicon) technology as in the zero-wait RTL benches
   of the study, now resolved at sub-cycle granularity.
4. The levels are divided into S bands of at most 17 levels by S - 1
   cuts.  On every net driven by a logic cell whose value crosses a cut,
   one DFFHQ per crossed cut is inserted (a register chain if several
   cuts are crossed); consumers read the register of the last cut they
   lie behind.  The cut levels are chosen by a dynamic programme that
   minimizes the number of registers under the band constraint
   (`_place_cuts`; the uniform placement at 17, 34, ... is the fallback
   on ties).  Flip-flop outputs and input pads are full-swing sources and
   are exempt: a path from them to a consumer is one stage.  Since every
   source is constant during the architectural cycle, a net that settles
   in sub-cycle j is constant from then on, so the registered copies are
   valid exactly when their consumers evaluate them.  The hold input of a
   hold multiplexer is read in every period and is never registered.
5. Fan-out legalization (INV trees) of the arch_en net and of rst runs
   before the levels are computed, so the trees are part of the schedule;
   the inverted rst that clears the ring is buffered after the ring is
   built (its S - 1 sinks exceed the limit for S > 5).  Cell ids of the
   input netlist are made canonical first, so the construction is the
   same for a netlist held by the flow and for one read back from
   build/*_mapped.json.

S is the smallest integer with 17 S >= max endpoint level, the endpoints
being the flip-flop D inputs (after hold-MUX insertion) and the primary
outputs.  The physical netlist is checked with `analyze` (depth <= 17 and
no fan-out violation) and by `verify_subcycle`, which runs it for S
periods from random architectural state, random pipeline-register
contents and an environment that returns garbage on every input whose
output-port dependencies do not yet show their final value, and compares
the next architectural state and the outputs of the last sub-cycle with
one evaluation of the original netlist.  The same netlist with a ring of
S - 1 phases must fail that check (test hook `force_subcycles`).

Timing model.  One physical period is the compliant 17-stage period
(171.02 us at full fan-out, `compliant_period_us`), f_phys = 5.847 kHz,
f_arch = f_phys / S, CPI_c = CPI x S; T_c, P and E/instr come from the
ordinary analysis of the physical netlist.
"""

from dataclasses import dataclass, field

import numpy as np

from .cells import CONSTRAINTS, LIBRARY, stage_delay_us
from .techmap import Netlist, C0, C1, _topo_order, legalize_fanout, PRIM_FN


__all__ = ["ENV_DEPS", "PipelineResult", "subcycle_pipeline",
           "verify_subcycle", "read_ports", "compliant_period_us"]


_SEQ = ("DFFHQ", "$_DFF_P_")

# Zero-delay environment model of the core's external world: each primary
# input port is a combinational function of the listed output ports
# (memory: read data / ack follow the address and the cycle strobe; the
# external digit-serial register file returns digit rf_index of rs1/rs2).
ENV_DEPS = {
    "ibus_ack":  ("ibus_cyc",),
    "ibus_rdat": ("ibus_cyc", "ibus_addr"),
    "dbus_ack":  ("dbus_cyc",),
    "dbus_rdat": ("dbus_cyc", "dbus_addr", "dbus_we"),
    "rf_rdig1":  ("rf_raddr1", "rf_index"),
    "rf_rdig2":  ("rf_raddr2", "rf_index"),
    "rst":       (),
    "clk":       (),
}


def compliant_period_us(constraints=CONSTRAINTS):
    """Physical clock period of a depth-compliant netlist: the paper's
    17-stage path at full fan-out (171.02 us)."""
    return constraints.max_logic_depth * stage_delay_us(
        constraints.max_fanout, constraints)


def read_ports(gates_json_path, top):
    """Port name -> list of bit tokens of the yosys gate-level netlist (the
    same tokens are the primary-input / primary-output nets of the mapped
    netlist; constant bits become the rails c0 / c1)."""
    import json
    with open(gates_json_path) as f:
        raw = json.load(f)
    mod = raw["modules"][top]
    ports = {}
    for pname, p in mod["ports"].items():
        ports[pname] = [(C1 if b == "1" else C0 if b in ("0", "x") else b)
                        for b in p["bits"]]
    return ports


@dataclass
class PipelineResult:
    netlist:      Netlist          # depth-compliant physical netlist
    subcycles:    int              # S
    dmax:         int
    arch_ffs:     list             # gids of the architectural flip-flops
    ring:         list             # Q nets of ring phases p[0..S-1]
    en_net:       object           # arch_en net (root of its buffer tree)
    arrival:      dict             # primary input net -> arrival level
    levels:       dict             # net -> scheduled logic level
    endpoint_level: int            # max level over endpoints
    cuts:         list             # cut levels (registers after level c)
    n_cut_regs:   int              # inserted pipeline DFFHQ
    n_hold_mux:   int              # hold MUX2 inserted
    n_holdless:   int              # architectural FFs without hold MUX
    n_ring_cells: int              # ring flip-flops + ring logic cells
    n_buffers:    int              # INV added for fan-out (en tree, Q pairs)
    cut_regs_per_cut: dict         # cut level -> registers on that cut
    physical:     set = field(default_factory=set)   # gids of ring/en logic
    notes:        list = field(default_factory=list)

    def subcycle_of_level(self, level):
        """Sub-cycle (0-based) in which a net of the given level settles:
        the number of cuts before it."""
        return sum(1 for c in self.cuts if c < level)


# ---------------------------------------------------------------- levels

def _heights(nl):
    """net -> longest number of cells from the net to an endpoint (a
    flip-flop D input or a primary output); criticality measure."""
    order = _topo_order(nl)
    cons = nl.consumer_map()
    h = {}
    for gid in reversed(order):
        kind, ins, out, clk = nl.gates[gid]
        best = 0
        for cg, pos in cons.get(out, ()):
            if nl.gates[cg][0] in _SEQ:
                continue                        # endpoint: height 0
            best = max(best, h.get(nl.gates[cg][2], 0) + 1)
        h[out] = best
    return h


def _levels(nl, arrival, physical):
    """Scheduled logic levels: flip-flop outputs, constants and the outputs
    of the physical-domain cells are level 0; primary inputs take their
    arrival level; every other cell is one deeper than its deepest input."""
    lvl = dict(arrival)
    for gid in _topo_order(nl):
        kind, ins, out, clk = nl.gates[gid]
        if gid in physical:
            lvl[out] = 0
            continue
        lvl[out] = max((lvl.get(i, 0) for i in ins), default=0) + 1
    return lvl


def _pi_nets(nl, ports, name):
    return [b for b in ports.get(name, ()) if b in nl.inputs
            and b not in (C0, C1)]


def _env_dep_map(nl, ports, env_deps):
    """PI net -> list of PO nets it is a zero-delay function of."""
    dep_of = {}
    for pname, deps in env_deps.items():
        for b in _pi_nets(nl, ports, pname):
            dep_of[b] = [x for d in deps for x in ports.get(d, ())
                         if x not in (C0, C1)]
    return dep_of


def _arrival_levels(nl, ports, env_deps, physical):
    """Fixed point of the environment model: PI level = max level of the
    output-port bits it is a function of."""
    pis = {b for b in nl.inputs if b not in (C0, C1) and b not in nl.clocks}
    arrival = {b: 0 for b in pis}
    dep_of = _env_dep_map(nl, ports, env_deps)
    for _ in range(len(env_deps) + 2):
        lvl = _levels(nl, arrival, physical)
        new = dict(arrival)
        for b in pis:
            new[b] = max((lvl.get(x, 0) for x in dep_of.get(b, ())),
                         default=0)
        if new == arrival:
            return arrival, lvl
        arrival = new
    raise RuntimeError("environment dependency model does not converge "
                       "(cyclic PO -> PI -> PO dependency)")


# ------------------------------------------------------------ construction

def _canonical(mapped):
    """Copy of `mapped` with compact cell ids (0..N-1 in the original
    order), so that the construction is identical for a netlist kept in
    memory by the flow and for one read back from build/*_mapped.json."""
    nl = Netlist(mapped.name)
    for gid in sorted(mapped.gates):
        k, i, o, c = mapped.gates[gid]
        nl.add(k, list(i), o, c)
    nl.inputs = set(mapped.inputs)
    nl.outputs = set(mapped.outputs)
    nl.clocks = set(mapped.clocks)
    nl._next_net = mapped._next_net
    return nl


def _build(base, ports, env_deps, constraints, hold, rst, en, physical0):
    """Insert the hold multiplexers of the flip-flops in `hold`, legalize
    fan-out, compute the schedule.  Returns (nl, physical, arrival, lvl,
    hold_mux gids, stats)."""
    nl = base.copy()
    physical = set(physical0)
    arch_ffs = sorted(g for g, (k, *_r) in nl.gates.items() if k in _SEQ)

    # hold multiplexers.  The MUX adds one load to Q; where Q already
    # drives max_fanout cells only its LEAST critical sink (fewest stages
    # to any endpoint) is moved, with the hold input, behind an INV pair
    # (the generic legalizer would put every sink behind a 2-level tree and
    # lengthen every path through the flip-flop by two stages).
    height = _heights(nl)
    lvl_pre = _levels(nl, {}, physical)        # preliminary (no MUX yet)
    dmax = constraints.max_logic_depth
    cons0 = nl.consumer_map()
    n_qbuf = 0
    hold_src = {}

    def victim_key(cp):
        # prefer a sink that stays in its band when pushed two levels
        # deeper (no extra cut register), then the least critical one
        out = nl.gates[cp[0]][2]
        l0 = lvl_pre.get(out, 1)
        return ((l0 + 1) // dmax != (l0 - 1) // dmax, height.get(out, 0))

    for gid in arch_ffs:
        if gid not in hold:
            continue
        kind, ins, out, _clk = nl.gates[gid]
        q = out
        sinks = [(cg, pos) for (cg, pos) in cons0.get(q, ())
                 if not (nl.gates[cg][0] in _SEQ and pos > 0)]
        src = q
        if len(sinks) >= constraints.max_fanout:
            victim = min(sorted(sinks), key=victim_key)
            t1, t2 = nl.new_net(), nl.new_net()
            nl.add("INV", [q], t1)
            nl.add("INV", [t1], t2)
            nl.gates[victim[0]][1][victim[1]] = t2
            src = t2
            n_qbuf += 2
        hold_src[gid] = src
    hold_mux = set()
    for gid, src in hold_src.items():
        d = nl.gates[gid][1][0]
        m = nl.new_net()
        hold_mux.add(nl.add("MUX2", [src, d, en], m))
        nl.gates[gid][1][0] = m

    # fan-out legalization of the new loads (en tree, rst)
    mark = nl._next_gid
    n_buf = legalize_fanout(nl, constraints.max_fanout)
    cons = nl.consumer_map()
    stack = [en]                     # the en tree carries the phase
    while stack:
        net = stack.pop()
        for cg, pos in cons.get(net, ()):
            if cg >= mark and nl.gates[cg][0] == "INV":
                physical.add(cg)
                stack.append(nl.gates[cg][2])

    arrival, lvl = _arrival_levels(nl, ports, env_deps, physical)
    stats = dict(n_hold=len(hold_mux), n_buf=n_buf + n_qbuf, n_qbuf=n_qbuf)
    return nl, physical, arrival, lvl, hold_mux, stats


def _endpoint_level(nl, lvl, arch_ffs):
    ends = [nl.gates[g][1][0] for g in arch_ffs]
    ends.extend(b for b in nl.outputs if b not in (C0, C1))
    return max(lvl.get(n, 0) for n in ends)


def _holdless_ok(nl, gid, lvl, S, dmax, physical, hold_mux):
    """Can architectural flip-flop `gid` run without a hold multiplexer?

    Without one it latches D at every edge, so its Q is the current state
    in sub-cycle 0 only and carries intermediate values afterwards.  That
    is harmless iff
      (i)   its next-state net lies in the last band (it is then settled
            when the architectural edge comes);
      (ii)  Q is not a primary output, and every endpoint reachable from Q
            through combinational cells -- a primary output, the B input
            of another flip-flop's hold multiplexer, or a flip-flop D
            input -- lies in the last band as well (endpoints of earlier
            bands are evaluated in the last sub-cycle from re-latched
            registers, which by then carry the intermediate values).
    Consumers of Q outside the first band then read a registered copy of
    Q captured after sub-cycle 0 (the cut registers are inserted on Q like
    on any logic-driven net)."""
    kind, ins, q, _c = nl.gates[gid]
    drv = nl.driver_map()
    mg = drv.get(ins[0])
    own_mux = mg if (mg is not None and mg in hold_mux) else None
    d = nl.gates[own_mux][1][1] if own_mux is not None else ins[0]
    last = dmax * (S - 1)
    if lvl.get(d, 0) <= last:                                 # (i)
        return False
    if q in nl.outputs:                                       # (ii)
        return False
    cons = nl.consumer_map()
    seen = set()
    stack = [q]
    while stack:
        net = stack.pop()
        if net in seen:
            continue
        seen.add(net)
        if net != q and net in nl.outputs and lvl.get(net, 0) <= last:
            return False                                      # (ii) PO
        for cg, pos in cons.get(net, ()):
            if cg in physical or cg == own_mux:
                continue
            k = nl.gates[cg][0]
            if k in _SEQ:
                if pos == 0 and lvl.get(net, 0) <= last:
                    return False                              # (ii) FF D
                continue
            if cg in hold_mux:
                if pos == 1 and lvl.get(net, 0) <= last:
                    return False                              # (ii) MUX B
                continue                       # (pos 0 never reachable)
            stack.append(nl.gates[cg][2])
    return True


def subcycle_pipeline(mapped, ports, env_deps=ENV_DEPS,
                      constraints=CONSTRAINTS, force_subcycles=None,
                      holdless=True):
    """Build the depth-compliant physical netlist of `mapped` (a mapped,
    fan-out-legalized netlist with the clock in `mapped.clocks`).

    `ports` is the port map of the gate-level netlist (`read_ports`).
    `holdless=False` gives every architectural flip-flop a hold MUX.
    `force_subcycles` overrides the ring length only (test hook: S - 1
    must fail `verify_subcycle`)."""
    dmax = constraints.max_logic_depth
    base = _canonical(mapped)
    base.name = f"{mapped.name}_pipelined"
    if not base.clocks:
        raise ValueError("mapped netlist has no clock net")
    clk = next(iter(base.clocks))
    rst_bits = _pi_nets(base, ports, "rst")
    if len(rst_bits) != 1:
        raise ValueError("expected exactly one rst input bit")
    rst = rst_bits[0]
    for gid, g in base.gates.items():
        if g[0] == "$_DFF_P_":
            g[0] = "DFFHQ"                     # library flip-flop
    arch_ffs = sorted(g for g, (k, *_r) in base.gates.items() if k in _SEQ)

    # ---- 1. ring-counter logic (S unknown yet: the OR2 input from p[S-1]
    #         is a placeholder patched below); arch_en = p[S-1] | rst
    p_last = base.new_net()
    en = base.new_net()
    g_or = base.add("OR2", [p_last, rst], en)
    nrst = base.new_net()
    g_nrst = base.add("INV", [rst], nrst)
    physical0 = {g_or, g_nrst}

    # ---- 2. hold multiplexers + schedule, with the hold-less choice
    #         iterated to a fixed point for the target S
    all_hold = {g for g in arch_ffs
                if base.gates[g][1][0] != base.gates[g][2]}

    def built(hold):
        r = _build(base, ports, env_deps, constraints, hold, rst, en,
                   physical0)
        l = _endpoint_level(r[0], r[3], arch_ffs)
        return r, l, max(-(-l // dmax), 1)

    (nl, physical, arrival, lvl, hold_mux, st), l_end, S_req = built(set())
    S_try = S_req                       # S without any hold-MUX penalty
    hold = set(all_hold)
    (nl, physical, arrival, lvl, hold_mux, st), l_end, S_req = built(hold)
    if holdless:
        done = False
        for _attempt in range(2):
            hold = set(all_hold)
            for _it in range(8):
                (nl, physical, arrival, lvl, hold_mux, st), l_end, S_req = \
                    built(hold)
                elig = {g for g in all_hold
                        if _holdless_ok(nl, g, lvl, S_try, dmax, physical,
                                        hold_mux)}
                new_hold = all_hold - elig
                if new_hold == hold:
                    break
                hold = new_hold
            if S_req == S_try:
                done = True
                break
            S_try += 1
        if not done:                              # pragma: no cover
            hold = set(all_hold)
            (nl, physical, arrival, lvl, hold_mux, st), l_end, S_req = \
                built(hold)
    holdless_ffs = all_hold - hold
    drv = nl.driver_map()
    S = S_req if force_subcycles is None else max(int(force_subcycles), 1)

    # ---- 3. ring counter p[0..S-1]
    ring = [nl.new_net() for _ in range(S)]
    ring_cells = 2                                 # OR2 + INV(rst)
    for i in range(S):
        if i == 0:
            physical.add(nl.add("DFFHQ", [en], ring[0], clk=clk))
            ring_cells += 1
        else:
            dn = nl.new_net()
            physical.add(nl.add("AND2", [ring[i - 1], nrst], dn))
            physical.add(nl.add("DFFHQ", [dn], ring[i], clk=clk))
            ring_cells += 2
    nl.gates[g_or][1][0] = ring[S - 1]
    # INV(rst) drives the S-1 ring AND2 gates: buffer it when S-1 exceeds
    # the fan-out limit (the only illegal net at this point; the core's
    # own rst sinks were legalized together with the OR2/INV above)
    before = set(nl.gates)
    legalize_fanout(nl, constraints.max_fanout)
    ring_buf = set(nl.gates) - before
    for g in ring_buf:
        if nl.gates[g][0] != "INV":
            raise RuntimeError("unexpected cell from ring buffering")
    physical |= ring_buf
    ring_cells += len(ring_buf)

    # ---- 4. cut registers on every logic-driven net crossing a cut
    edges = []                           # (gid, pos, net, dl, l_out)
    span = {}                            # net -> (dl, max l_out)
    for gid, (kind, ins, out, _c) in list(nl.gates.items()):
        if gid in physical or kind in _SEQ:
            continue
        l_out = lvl.get(out, 0)
        for pos, net in enumerate(ins):
            d = drv.get(net)
            if net in (C0, C1) or d is None:          # constants, PI: exempt
                continue
            if d in physical:
                continue
            if nl.gates[d][0] in _SEQ and d not in holdless_ffs:
                continue                                  # FF Q: exempt
            if gid in hold_mux and pos == 0:
                # the hold input (Q, or its INV pair) is read in EVERY
                # period, including sub-cycle 0 before any cut register has
                # captured the new state: never registered
                continue
            dl = lvl.get(net, 0)
            if l_out - 1 < dl:
                continue
            edges.append((gid, pos, net, dl, l_out))
            s0, s1 = span.get(net, (dl, l_out))
            span[net] = (min(s0, dl), max(s1, l_out))
    cuts = _place_cuts(span, S_req, dmax, l_end)
    cut_regs = {c: 0 for c in cuts}
    reg_chain = {}                       # net -> {cut: Q net of register}
    consumers = []                       # (gid, pos, net, cut)
    for gid, pos, net, dl, l_out in edges:
        crossed = [c for c in cuts if dl <= c <= l_out - 1]
        if not crossed:
            continue
        chain = reg_chain.setdefault(net, {})
        for c in crossed:
            chain.setdefault(c, None)
        consumers.append((gid, pos, net, crossed[-1]))
    n_cut = 0
    for net, chain in reg_chain.items():
        prev = net
        for c in sorted(chain):
            q = nl.new_net()
            nl.add("DFFHQ", [prev], q, clk=clk)
            chain[c] = q
            prev = q
            cut_regs[c] += 1
            n_cut += 1
    for gid, pos, net, c in consumers:
        nl.gates[gid][1][pos] = reg_chain[net][c]

    # ---- 5. cut insertion only splits sinks: no further buffering may be
    #         needed
    n_more = legalize_fanout(nl, constraints.max_fanout)
    if n_more:
        raise RuntimeError(f"unexpected fan-out violations after cut "
                           f"insertion ({n_more} buffers)")

    res = PipelineResult(
        netlist=nl, subcycles=S, dmax=dmax, arch_ffs=arch_ffs, ring=ring,
        en_net=en, arrival=arrival, levels=lvl, endpoint_level=l_end,
        cuts=cuts, n_cut_regs=n_cut, n_hold_mux=st["n_hold"],
        n_holdless=len(holdless_ffs), n_ring_cells=ring_cells,
        n_buffers=st["n_buf"], cut_regs_per_cut=cut_regs,
        physical=physical)
    res.notes.append(
        f"S = {S} sub-cycles (max endpoint level {l_end}, cut"
        f"{'s' if len(cuts) != 1 else ''} after level "
        f"{', '.join(map(str, cuts)) or '-'}); "
        f"{n_cut} pipeline DFFHQ on {len(reg_chain)} nets, "
        f"{st['n_hold']} hold MUX2 ({len(holdless_ffs)} flip-flops "
        f"without), ring counter of {S} DFFHQ, {st['n_buf']} buffer INV "
        f"({st['n_qbuf']} on flip-flop outputs)")
    return res


def _place_cuts(span, S, dmax, l_end):
    """Choose the S-1 cut levels c_1 < ... < c_{S-1}: a register after
    level c_k on every net whose driver level <= c_k < its deepest
    consumer level.  Every band must be at most `dmax` levels deep
    (c_1 <= dmax, c_{k+1} - c_k <= dmax, l_end - c_{S-1} <= dmax) and
    c_k <= k * dmax keeps the last band at least as large as the uniform
    one assumed by the hold-less analysis.  Among the admissible
    placements the one with the fewest registers is taken (dynamic
    programme over the cut levels); ties go to the uniform placement."""
    if S <= 1:
        return []
    diff = [0] * (l_end + 2)
    for dl, lm in span.values():
        lo, hi = max(dl, 1), min(lm - 1, l_end)
        if lo > hi:
            continue
        diff[lo] += 1
        diff[hi + 1] -= 1
    cross = [0] * (l_end + 1)
    run = 0
    for c in range(l_end + 1):
        run += diff[c]
        cross[c] = run
    n_cuts = S - 1
    best = {}                     # k-th cut at level c -> (cost, levels)
    for c in range(1, min(dmax, l_end - 1) + 1):
        best[c] = (cross[c], [c])
    for k in range(2, n_cuts + 1):
        nxt = {}
        for c in range(k, min(k * dmax, l_end - 1) + 1):
            cand = None
            for cp in range(max(c - dmax, 1), c):
                if cp in best:
                    cost = best[cp][0] + cross[c]
                    if cand is None or cost < cand[0] or \
                            (cost == cand[0] and cp == (k - 1) * dmax):
                        cand = (cost, best[cp][1] + [c])
            if cand is not None:
                nxt[c] = cand
        best = nxt
    uniform = [k * dmax for k in range(1, n_cuts + 1)]
    final = [(v[0], v[1] != uniform, v[1]) for c, v in best.items()
             if l_end - c <= dmax]
    if not final:
        raise RuntimeError("no admissible cut placement")
    return min(final)[2]


# ---------------------------------------------------------- verification

def _ff_gids(nl):
    return sorted(g for g, (k, *_r) in nl.gates.items() if k in _SEQ)


def _eval_comb(nl, order, fns, vals):
    for gid in order:
        kind, ins, out, clk = nl.gates[gid]
        vals[out] = fns[kind](*(vals[n] for n in ins))


def verify_subcycle(mapped, pres, ports, patterns=4096, seed=0x5EED2D,
                    env_deps=ENV_DEPS, garbage_env=True):
    """Sequential equivalence of the physical netlist against the original
    mapped netlist, bit-parallel over `patterns` random cases:

      * random architectural state (Q of every original flip-flop), random
        contents of every pipeline register, ring counter at phase 0,
        rst = 0, random primary inputs;
      * the environment is emulated at sub-cycle granularity: in every
        period an environment-driven input carries its true value only in
        the bit lanes where all output-port bits it depends on show the
        value of the reference evaluation, and random garbage elsewhere
        (`garbage_env=False` holds all inputs constant instead);
      * the physical netlist runs S periods; its architectural state after
        the S-th edge and its primary outputs in the last sub-cycle must
        equal the next state / outputs of one evaluation of `mapped`.

    Returns the number of patterns; raises AssertionError on mismatch."""
    words = (patterns + 63) // 64
    rng = np.random.default_rng(seed)
    rnd = lambda: rng.integers(0, 1 << 64, size=words, dtype=np.uint64)

    fns = dict(PRIM_FN)
    for name, c in LIBRARY.items():
        if not c.seq:
            fns[name] = c.fn
    S = pres.subcycles
    nl = pres.netlist
    order_ref = _topo_order(mapped)
    order_phy = _topo_order(nl)
    zeros = np.zeros(words, dtype=np.uint64)
    ones = ~zeros

    # --- reference: one evaluation of the original next-state function
    ref_vals = {C0: zeros, C1: ones}
    pi_true = {}
    rst = _pi_nets(mapped, ports, "rst")[0]
    for net in mapped.inputs:
        if net in (C0, C1) or net in mapped.clocks:
            continue
        pi_true[net] = zeros if net == rst else rnd()
    ref_vals.update(pi_true)
    arch_q = {}
    for gid in _ff_gids(mapped):
        arch_q[mapped.gates[gid][2]] = rnd()
    ref_vals.update(arch_q)
    _eval_comb(mapped, order_ref, fns, ref_vals)
    ref_next = {mapped.gates[g][2]: ref_vals[mapped.gates[g][1][0]]
                for g in _ff_gids(mapped)}
    po_nets = [b for b in mapped.outputs if b not in (C0, C1)]
    ref_po = {b: ref_vals.get(b, pi_true.get(b, zeros)) for b in po_nets}

    # --- physical netlist over S periods
    vals = {C0: zeros, C1: ones}
    vals.update(pi_true)
    ffs = _ff_gids(nl)
    for gid in ffs:
        q = nl.gates[gid][2]
        vals[q] = arch_q[q] if q in arch_q else rnd()
    for i, q in enumerate(pres.ring):
        vals[q] = ones if i == 0 else zeros
    dep_of = _env_dep_map(mapped, ports, env_deps)
    garbage = {b: rnd() for b in pi_true}

    def env_inputs():
        """inputs true where their PO dependencies are final, else garbage"""
        for b, deps in dep_of.items():
            if b == rst or not deps:
                continue
            ok = ones
            for x in deps:
                got = vals.get(x, pi_true.get(x, zeros))
                ok = ok & ~(got ^ ref_po[x])
            vals[b] = (pi_true[b] & ok) | (garbage[b] & ~ok)

    for sub in range(S):
        if garbage_env:
            # two-phase evaluation like the gate-level benches: outputs
            # from the current state, environment response, re-evaluation
            for b in dep_of:
                if b != rst and dep_of[b]:
                    vals[b] = garbage[b]
            _eval_comb(nl, order_phy, fns, vals)
            env_inputs()
        _eval_comb(nl, order_phy, fns, vals)
        if sub == S - 1:
            for b, want in ref_po.items():
                got = vals.get(b, pi_true.get(b, zeros))
                if not np.array_equal(got, want):
                    raise AssertionError(
                        f"primary output {b} differs in sub-cycle {S - 1}")
        nxt = {nl.gates[g][2]: vals[nl.gates[g][1][0]] for g in ffs}
        vals.update(nxt)
        for i, q in enumerate(pres.ring):        # one-hot ring advances
            exp = ones if i == (sub + 1) % S else zeros
            if not np.array_equal(vals[q], exp):
                raise AssertionError("ring counter is not one-hot")
    for q, want in ref_next.items():
        if not np.array_equal(vals[q], want):
            raise AssertionError(
                f"architectural next state differs at flip-flop Q {q}")
    return words * 64
