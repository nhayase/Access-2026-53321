"""Human-readable synthesis report, benchmarked against RV32-WUJI."""

from .cells import CONSTRAINTS, PAPER_REFERENCE, LIBRARY, EXCLUDED_CELLS


__all__ = ["format_report"]


def _ok(flag):
    return "PASS" if flag else "FAIL"


def format_report(res, constraints=CONSTRAINTS, paper=PAPER_REFERENCE):
    c, p = constraints, paper
    lines = []
    w = lines.append
    w("=" * 72)
    w(f"M2D synthesis report -- {res.name}")
    w("target: MoS2 E/D-NMOS 2D-semiconductor process (RV32-WUJI PDK)")
    w("=" * 72)

    w("")
    w("Cell usage (2D_NMOS_lib):")
    for kind, n in res.cell_counts.items():
        t = LIBRARY[kind].transistors * n
        nm = LIBRARY[kind].noise_margin
        nm_s = f"NM={nm:.3f} V" if nm is not None else ""
        w(f"  {kind:<8} x {n:>5}   {t:>6} T   {nm_s}")
    w(f"  {'TOTAL':<8}   {res.n_cells:>5}   {res.transistors:>6} T"
      f"   ({res.n_seq} flip-flops)")

    w("")
    w("Design-rule checks (paper constraints):")
    w(f"  logic depth        {res.logic_depth:>8} stages   "
      f"(limit {c.max_logic_depth})   {_ok(res.depth_ok)}")
    w(f"  max fan-out        {res.fanout_max:>8} loads    "
      f"(limit {c.max_fanout})    {_ok(res.fanout_ok)}")
    nm = res.min_noise_margin
    w(f"  min noise margin   {nm:>8.3f} V        "
      f"(limit {c.min_noise_margin:.1f} V = 5% Vdd)  "
      f"{_ok(nm >= c.min_noise_margin)}")
    if res.fanout_violations:
        w("  fan-out violations:")
        for net, n in res.fanout_violations[:10]:
            w(f"    net {net}: {n} loads")

    w("")
    w("Timing (linear model calibrated to the paper, Vdd = 4 V):")
    w(f"  critical path delay  {res.delay_us:>10.1f} us")
    w(f"  f_max                {res.fmax_hz:>10.1f} Hz")
    w(f"  recommended f_op     {p['operating_hz']:>10.1f} Hz "
      f"(paper operating point)")
    w("  critical path (cell, fan-out stage delay):")
    for kind, net, d in res.critical_cells[-min(len(res.critical_cells), 20):]:
        w(f"    {kind:<8} -> {net}   {d:.2f} us")

    w("")
    w("Power (static-dominated E/D-NMOS):")
    w(f"  estimated static power  {res.power_mw:.3f} mW "
      f"({c.static_nw_per_t:.1f} nW/transistor)")

    w("")
    w("Comparison with RV32-WUJI (Nature 640, 654 (2025)):")
    w(f"  {'metric':<24}{'this design':>16}{'RV32-WUJI':>16}")
    w(f"  {'transistors':<24}{res.transistors:>16}{p['transistors']:>16}")
    w(f"  {'max path delay (us)':<24}{res.delay_us:>16.1f}"
      f"{p['max_path_delay_us']:>16.1f}")
    w(f"  {'logic depth (stages)':<24}{res.logic_depth:>16}"
      f"{p['max_logic_depth']:>16}")
    w(f"  {'max fan-out':<24}{res.fanout_max:>16}{p['max_fanout']:>16}")
    w(f"  {'power (mW)':<24}{res.power_mw:>16.3f}{p['power_mw']:>16.3f}")
    w(f"  {'Vdd (V)':<24}{c.vdd:>16.1f}{p['vdd']:>16.1f}")
    w("  note: the RV32-WUJI transistor count covers the whole chip; the")
    w("  register file of this design is off-chip (as its 1,024 state bits")
    w("  alone would exceed the 2D transistor budget, cf. Suppl. Fig. 7).")

    w("")
    w("Cells excluded from the PDK (noise margin < 5% Vdd, Fig. 3b):")
    w("  " + ", ".join(f"{k} ({v:.3f} V)"
                       for k, v in EXCLUDED_CELLS.items()))
    if res.notes:
        w("")
        for n in res.notes:
            w(f"note: {n}")
    w("=" * 72)
    return "\n".join(lines)
