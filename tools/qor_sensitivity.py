#!/usr/bin/env python3
"""QoR sensitivity of the defect-density ladder (Section VI-D).

WHY THIS EXISTS
---------------
Section III-D (V2c) shows that the mapper's quality-of-results (QoR)
overhead against ABC is approximately uniform in width, and concludes that
it cancels from every serial-to-parallel RATIO.  That is correct for
ratios.  It is NOT correct for the yield axis, because the defect-density
boundary between two designs is

    d* = ln(thr_i / thr_j) / (T_i - T_j)                            (5)

which depends on a DIFFERENCE of transistor counts.

DIRECTION OF THE SCALING -- read this before the table.  This flow's
transistor counts are the LARGE ones: a mapper q times better produces
T' = T / q, which shrinks the difference by q and therefore MULTIPLIES
every boundary by exactly q:

    d*(q) = q d*(1)      for a mapper q times better than this flow.

Physically this is the only possible sign: an implementation that needs
fewer transistors tolerates a HIGHER defect density before serialization
pays off, so the ladder rises with q and the exit yields RELAX.  (The
inverse statement, d* -> d*/q, describes inflating this flow's counts
still further, which is not what the q column below tabulates.)

Since d* is what the article inverts into the headline exit yields
exp(-d*), the exit thresholds inherit the mapper's QoR factor.  This
script quantifies that, so the article can report it rather than be
told about it by a reviewer.

TWO SCALING MODELS
------------------
uniform      T'(q) = T / q.
             Matches the empirical observation that the ABC overhead is
             flat across widths.  Pessimistic: it assumes a better mapper
             would also shrink the flip-flops, which it cannot.

comb-only    T'(q) = T_ff + (T - T_ff) / q,  T_ff = 18 x n_DFF.
             The 18 T/flip-flop cost is fixed by the library; only
             combinational logic is compressible.  This is the physically
             defensible model and gives a smaller shift.

CALIBRATION OF q
----------------
q is MEASURED, not bounded.  Both mappers' netlists are put through the
same even-level inverter-tree fan-out legalization pass, so the counts
compared below satisfy the same fan-out <= 4 design rule.  From
results/abc_crosscheck.md, fan-out-legalized transistor counts:

    design          this flow      yosys+ABC       q
    W = 1  ripple       10,474          7,056    1.484
    W = 32 ripple       25,679         17,864    1.437
    W = 32 prefix       27,195         17,166    1.584

and against the hand-optimized fabricated chip at W = 1,
10,474 / 5,931 = 1.766.

Earlier versions of this study compared the UNLEGALIZED ABC netlists
(6,490 / 15,718 / 15,326 T at fan-out 40 to 84 on 61 to 214 nets) and
could therefore only call q an upper bound.  Legalizing both sides costs
ABC +8.7 % to +13.6 % of its transistors and this flow +9.2 %, so the
ratio barely moves (1.478 -> 1.484 at W = 1) but is now a like-for-like
measurement rather than a bound.

USAGE
-----
    python3 tools/qor_sensitivity.py                # writes results/qor_sensitivity.md
    python3 tools/qor_sensitivity.py --csv X --out Y
"""

import argparse
import csv
import math
import os


# Published wafer-scale anchor of Ao et al. (Nature 640, 654 (2025)).
#
# ONLY the per-transistor figure is used.  Ao et al. report a wafer-scale
# functional yield of 99.92 % PER TRANSISTOR, which is unambiguous as to
# the unit it is normalized to, and
#
#   ANCHOR = -ln(0.9992) = 8.00e-4 defects per transistor.
#
# The other yield figures of the same work (898/900 inverters = 99.77 %,
# 144-T and 1,152-T register blocks of Supplementary Fig. 7) place the
# process at the same or a higher defect density; they are analyzed in
# tools/block_yield.py and do not enter the ladders computed here.
ANCHOR = -math.log(0.9992)

T_PER_FF = 18


def load_rows(path):
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            rows.append(dict(
                width=int(r["width"]),
                adder=r["adder"],
                dff=int(r["dff"]),
                transistors=int(r["transistors"]),
                cpi_geo=float(r["cpi_geo"]),
                fmax_hz=float(r["fmax_hz"]),
            ))
    for r in rows:
        r["thr_1k"] = 1000.0 / r["cpi_geo"]
        r["thr_fmax"] = r["fmax_hz"] / r["cpi_geo"]
    return rows


def scale(rows, q, model):
    out = []
    for r in rows:
        s = dict(r)
        if model == "uniform":
            s["T"] = r["transistors"] / q
        elif model == "comb":
            t_ff = T_PER_FF * r["dff"]
            s["T"] = t_ff + (r["transistors"] - t_ff) / q
        else:
            raise ValueError(model)
        out.append(s)
    return out


def envelope(designs, thr_key, d_lo=1e-7, d_hi=3e-3, n=4000):
    """Upper envelope of exp(-dT)*thr; returns [(design, d_switch), ...].

    Same construction as study._envelope_d, restated here so that this
    script is readable on its own.
    """
    seq = []
    for i in range(n + 1):
        d = d_lo * (d_hi / d_lo) ** (i / n)
        best = max(designs, key=lambda r: math.exp(-d * r["T"]) * r[thr_key])
        if not seq or seq[-1][0] is not best:
            seq.append((best, d))
    out = []
    for j, (des, _) in enumerate(seq):
        if j == 0:
            out.append((des, None))
        else:
            prev = seq[j - 1][0]
            d_star = (math.log(prev[thr_key] / des[thr_key])
                      / (prev["T"] - des["T"]))
            out.append((des, d_star))
    return out


def ladder(rows, q, model, thr_key):
    env = envelope(scale(rows, q, model), thr_key)
    return [(f"W={d['width']} {d['adder']}", ds) for d, ds in env]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="results/study.csv")
    ap.add_argument("--out", default="results/qor_sensitivity.md")
    args = ap.parse_args()

    rows = load_rows(args.csv)
    qs = [1.0, 1.25, 1.48, 1.60, 1.77, 2.00]
    tags = {1.0: "as reported (this flow)",
            1.48: "measured vs. legalized yosys+ABC",
            1.77: "measured vs. hand-optimized chip at W = 1"}

    L = []
    w = L.append
    w("QoR sensitivity of the defect-density ladder\n")
    w("\nThe boundary d* = ln(thr_i/thr_j)/(T_i - T_j) depends on a "
      "DIFFERENCE of\ntransistor counts, so the mapper's QoR overhead does "
      "NOT cancel from it, as it\ndoes from every serial-to-parallel ratio. "
      "  For a mapper q times BETTER than this\nflow, T -> T/q and the "
      "boundary scales exactly as d*(q) = q d*(1), so the ladder\nrises "
      "with q and the exit yields relax.  q is\nmeasured "
      "between fan-out-legalized netlists on both sides (see the module\n"
      "docstring); it is no longer an upper bound.\n")

    for model, mname in (("uniform", "uniform inflation T' = T/q"),
                         ("comb", "combinational-only T' = T_ff + "
                                  "(T - T_ff)/q")):
        for thr_key, opname in (("thr_fmax", "f_max operation"),
                                ("thr_1k", "fixed 1 kHz clock")):
            w(f"\n## {mname}, {opname}\n\n")
            w("| q | " + " | ".join(
                f"switch {i}" for i in range(1, 4)) +
              " | exit yields (per transistor) | margin to the 2025 anchor "
              "|\n")
            w("|--:|" + "--:|" * 3 + ":--|:--|\n")
            for q in qs:
                lad = ladder(rows, q, model, thr_key)
                ds = [d for _, d in lad if d is not None]
                cells = [f"{d * 1e6:.0f}" for d in ds[:3]]
                cells += ["--"] * (3 - len(cells))
                ys = " / ".join(f"{100 * math.exp(-d):.3f} %"
                                for d in ds[:3])
                marg = f"x{ANCHOR / max(ds):.1f}" if ds else "--"
                note = f"  ({tags[q]})" if q in tags else ""
                w(f"| {q:.2f}{note} | " + " | ".join(cells) +
                  f" | {ys} | {marg} |\n")
            w("\nSwitch columns are defects per 10^6 transistors at the "
              "successive envelope\nboundaries (widest first).  The margin "
              "column is the ratio of the published\nper-transistor anchor "
              f"({ANCHOR * 1e6:.0f} defects per 10^6 T) to the last "
              "boundary, i.e. how\nfar inside the bit-serial region the "
              "2025 process still sits.\n")

    w("\n## Reading\n")
    w("\nUnder the Poisson model the retrodiction is mapper-independent: "
      "across every q\nconsidered, and under both scaling models, the "
      "published per-transistor anchor\nremains strictly inside the "
      "bit-serial region, so the conclusion that the map\nselects the "
      "width that was in fact built does not depend on the mapper.  What\n"
      "DOES depend on the mapper is the QUANTITATIVE exit threshold: the "
      "values quoted\nin the article are computed at q = 1, i.e. with this "
      "flow's own transistor counts,\nand a better mapper moves them "
      "upward in defect density and downward in required\nyield.  The "
      "article therefore quotes the exit yields with their q dependence "
      "stated\nrather than to five significant figures as if they were "
      "mapper-independent.\n")
    w("\nThe mapper axis is NOT the binding one, however.  Defect "
      "clustering moves the\nsame boundaries in the same direction and by "
      "considerably more; see\nresults/nb_sensitivity.md, which sweeps it "
      "and reports the break-even.\n")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        f.write("".join(L))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
