"""
Netlist analysis + design-rule checks against the RV32-WUJI constraints.

Computed per mapped netlist:

  * transistor budget and cell-type histogram;
  * combinational logic depth between flip-flops (paper limit: 17 stages);
  * fan-out distribution (paper limit: 4 loads / 10 pF);
  * critical path delay with the calibrated linear delay model
    (paper: 171 us maximum path delay at Vdd = 4 V) and f_max;
  * static power estimate (paper: 0.431 mW at 1 kHz, static-dominated);
  * minimum noise margin over the cells actually used.

The level/arrival computation is vectorized with NumPy: gates are sorted
topologically once, then levels and arrival times are propagated over integer
arrays, which keeps analysis of multi-thousand-gate netlists in the
millisecond range.
"""

from dataclasses import dataclass, field

import numpy as np

from .cells import LIBRARY, CONSTRAINTS, stage_delay_us
from .techmap import _topo_order


__all__ = ["AnalysisResult", "analyze"]


@dataclass
class AnalysisResult:
    name:            str
    cell_counts:     dict
    n_cells:         int
    n_seq:           int
    transistors:     int
    logic_depth:     int
    critical_cells:  list
    delay_us:        float
    fmax_hz:         float
    fanout_max:      int
    fanout_hist:     dict
    fanout_violations: list
    depth_ok:        bool
    fanout_ok:       bool
    min_noise_margin: float
    power_mw:        float
    notes:           list = field(default_factory=list)


def analyze(nl, constraints=CONSTRAINTS):
    cons_map = nl.consumer_map()

    # ---- fan-out (internal data pins; clock pins of DFFHQ are excluded,
    #      the chip is driven by an external clock; primary outputs drive
    #      bond pads and are likewise excluded; the constant nets c0/c1 are
    #      the GND/Vdd power rails, not logic-unit outputs)
    fanout = {}
    for net, pins in cons_map.items():
        n = sum(1 for (gid, pos) in pins
                if not (nl.gates[gid][0] == "DFFHQ" and pos > 0))
        fanout[net] = n

    fo_hist = {}
    fo_viol = []
    fo_max = 0
    drv = nl.driver_map()
    for net, n in fanout.items():
        if net in nl.clocks or net in ("c0", "c1") or n == 0:
            continue
        fo_hist[n] = fo_hist.get(n, 0) + 1
        fo_max = max(fo_max, n)
        if n > constraints.max_fanout:
            fo_viol.append((net, n))

    # ---- topological levels + arrival times (NumPy propagation)
    order = _topo_order(nl)                       # combinational gates only
    idx = {gid: i for i, gid in enumerate(order)}
    n = len(order)
    level   = np.zeros(n, dtype=np.int32)
    arrival = np.zeros(n, dtype=np.float64)
    stage   = np.zeros(n, dtype=np.float64)
    pred    = np.full(n, -1, dtype=np.int64)

    seq_kinds = ("DFFHQ", "$_DFF_P_")
    for i, gid in enumerate(order):
        kind, ins, out, clk = nl.gates[gid]
        stage[i] = stage_delay_us(max(fanout.get(out, 1), 1), constraints)
        best_l, best_t, best_p = 0, 0.0, -1
        for net in ins:
            d = drv.get(net)
            if d is None or nl.gates[d][0] in seq_kinds:
                continue                          # PI / state bit: level 0
            j = idx[d]
            if level[j] > best_l:
                best_l = level[j]
            if arrival[j] > best_t:
                best_t, best_p = arrival[j], j
        # longest combinational chain ending at this gate, counted in
        # logic stages: one more than the deepest driving gate (a gate fed
        # only by primary inputs / flip-flop outputs is at level 1).
        level[i]   = best_l + 1
        arrival[i] = best_t + stage[i]
        pred[i]    = best_p

    # depth / delay measured at flip-flop D inputs and primary outputs,
    # including the clk-to-Q stage of the launching flip-flop
    clkq = stage_delay_us(constraints.max_fanout, constraints)
    depth = 0
    t_comb = 0.0
    crit_end = -1
    endpoints = []
    for gid, (kind, ins, out, clk) in nl.gates.items():
        if kind in seq_kinds:
            endpoints.append(ins[0])
    endpoints.extend(nl.outputs)
    for net in endpoints:
        d = drv.get(net)
        if d is None or nl.gates[d][0] in seq_kinds:
            continue
        j = idx[d]
        if level[j] > depth:
            depth = int(level[j])
        if arrival[j] > t_comb:
            t_comb, crit_end = float(arrival[j]), j

    # critical path back-trace
    crit = []
    j = crit_end
    while j >= 0:
        kind, ins, out, clk = nl.gates[order[j]]
        crit.append((kind, out, float(stage[j])))
        j = int(pred[j])
    crit.reverse()

    delay = clkq + t_comb
    fmax = 1e6 / delay if delay > 0 else float("inf")

    # ---- area / power / noise margins
    counts = nl.counts()
    transistors = nl.transistors()
    n_seq = counts.get("DFFHQ", 0)
    power = transistors * constraints.static_nw_per_t * 1e-6   # mW
    nms = [LIBRARY[k].noise_margin for k in counts
           if k in LIBRARY and LIBRARY[k].noise_margin is not None]
    min_nm = min(nms) if nms else float("nan")

    notes = []
    if any(net in nl.inputs for net, _ in fo_viol):
        notes.append("some fan-out violations originate from primary inputs "
                     "(external drivers assumed)")
    notes.append(f"clk-to-Q of the launching DFFHQ modeled as one fully "
                 f"loaded stage ({clkq:.2f} us)")

    return AnalysisResult(
        name=nl.name,
        cell_counts=dict(sorted(counts.items())),
        n_cells=len(nl.gates),
        n_seq=n_seq,
        transistors=transistors,
        logic_depth=depth,
        critical_cells=crit,
        delay_us=delay,
        fmax_hz=fmax,
        fanout_max=fo_max,
        fanout_hist=dict(sorted(fo_hist.items())),
        fanout_violations=sorted(fo_viol, key=lambda t: -t[1]),
        depth_ok=depth <= constraints.max_logic_depth,
        fanout_ok=not fo_viol,
        min_noise_margin=min_nm,
        power_mw=power,
        notes=notes,
    )
