#!/usr/bin/env python3
"""Defect-clustering sensitivity of the yield envelope (Section VI-D).

WHY THIS EXISTS
---------------
The article's yield axis uses the per-transistor Poisson model

    Y(T) = exp(-d T)                                                  (5)

which is the zero-clustering extreme.  Real defect fields cluster, and the
classical remedy is the negative-binomial (Murphy / Stapper) form

    Y(T) = (1 + d T / alpha)^(-alpha),                                (5')

with the clustering parameter alpha -> infinity recovering Poisson and small
alpha meaning strong clustering.  Clustering RAISES the yield of the LARGER
design more than that of the smaller one, so it works AGAINST serialization:
it pushes every envelope boundary to a HIGHER defect density and therefore
SHRINKS the margin by which the published 2025 anchor sits inside the
bit-serial region.  Simply asserting that Poisson is "conservative" is
therefore not a defence of the retrodiction -- it is an admission that the
model is biased towards the very answer the retrodiction reports.

This script removes the assertion and replaces it with a sweep.  No
die-level yield data are required: alpha is swept over the whole range that
the silicon literature ever uses, and the question asked is whether the
retrodiction survives across it.

WHY THE ANCHOR ITSELF IS ESSENTIALLY alpha-INDEPENDENT
------------------------------------------------------
The anchor is a PER-TRANSISTOR functional yield, i.e. (5') evaluated at
T = 1:

    d = alpha ( Y_T^(-1/alpha) - 1 ).

The relative difference from -ln(Y_T) is about -ln(Y_T) / (2 alpha) =
4e-4 / alpha: 0.04 % at alpha = 1 and 0.08 % at alpha = 0.5, the strongest
clustering of the sweep.  The anchor
therefore stays put and only the BOUNDARIES move -- which is exactly what
makes the sweep a clean one-sided test.

COMBINED WITH MAPPER QUALITY
----------------------------
Clustering and mapper quality both move the boundaries upward relative to
the anchor, so the worst case for the retrodiction is the corner
(strongest clustering, best mapper).  The final table evaluates that corner
explicitly rather than the two effects separately.

USAGE
-----
    python3 tools/nb_sensitivity.py               # writes results/nb_sensitivity.md
    python3 tools/nb_sensitivity.py --csv X --out Y
"""

import argparse
import csv
import math
import os


# Published wafer-scale anchor of Ao et al. (Nature 640, 654 (2025)):
# a PER-TRANSISTOR functional yield of 99.92 %.  This is the only anchor the
# break-even values computed here are compared with the clustering parameter
# fitted to the register blocks of the same work in tools/block_yield.py.
ANCHOR_YT = 0.9992

T_PER_FF = 18

# Transistor count of the fabricated RV32-WUJI die, used to report the die
# yield each clustering parameter implies at the same anchor.
T_FAB_CHIP = 5931

# Clustering parameters.  Stapper's silicon fits sit around alpha = 1 to 5;
# alpha = 0.5 is stronger clustering than is normally reported anywhere, and
# alpha = 1e6 is numerically indistinguishable from Poisson.
ALPHAS = [1e6, 10.0, 5.0, 3.0, 2.0, 1.0, 0.5]


def anchor_d(alpha):
    """Per-transistor defect density implied by the published yield under
    the negative-binomial model with clustering parameter `alpha`."""
    if alpha > 1e5:
        return -math.log(ANCHOR_YT)
    return alpha * (ANCHOR_YT ** (-1.0 / alpha) - 1.0)


def log_yield_nb(d, T, alpha):
    """log of (5'); used directly so that the deep-subthreshold tail of the
    envelope search does not underflow to zero."""
    if alpha > 1e5:
        return -d * T
    return -alpha * math.log1p(d * T / alpha)


def yield_nb(d, T, alpha):
    return math.exp(max(log_yield_nb(d, T, alpha), -700.0))


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


def scale(rows, q, model="comb"):
    """Transistor counts of a mapper `q` times better than this flow."""
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


def _cross(a, b, alpha, thr_key, lo=1e-9, hi=1e-1):
    """Defect density at which designs a and b have equal expected
    throughput under (5').  Bisection on the sign of the difference."""
    def f(d):
        return ((log_yield_nb(d, a["T"], alpha) + math.log(a[thr_key]))
                - (log_yield_nb(d, b["T"], alpha) + math.log(b[thr_key])))
    if f(lo) * f(hi) > 0:
        return None
    for _ in range(200):
        mid = math.sqrt(lo * hi)
        if f(lo) * f(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return math.sqrt(lo * hi)


def envelope(designs, alpha, thr_key, d_lo=1e-7, d_hi=3e-3, n=6000):
    """Upper envelope of Y(d, T) * throughput; returns [(design, d_switch)].

    Same construction as study._envelope_d, with (5) replaced by (5')."""
    seq = []
    for i in range(n + 1):
        d = d_lo * (d_hi / d_lo) ** (i / n)
        best = max(designs,
                   key=lambda r: (log_yield_nb(d, r["T"], alpha)
                                  + math.log(r[thr_key])))
        if not seq or seq[-1][0] is not best:
            seq.append((best, d))
    out = []
    for j, (des, _) in enumerate(seq):
        if j == 0:
            out.append((des, None))
        else:
            out.append((des, _cross(seq[j - 1][0], des, alpha, thr_key)))
    return out


def ladder(rows, alpha, thr_key, q=1.0, model="comb"):
    env = envelope(scale(rows, q, model), alpha, thr_key)
    return [(f"W={d['width']} {d['adder']}", ds) for d, ds in env]


def selected_at_anchor(rows, alpha, thr_key, q=1.0, model="comb"):
    """The design the envelope selects AT the published anchor.  This is the
    direct form of the retrodiction test: it does not depend on how many
    boundaries happen to remain inside the swept range, which is what makes
    it usable when strong clustering collapses the envelope."""
    d = anchor_d(alpha)
    des = scale(rows, q, model)
    b = max(des, key=lambda r: (log_yield_nb(d, r["T"], alpha)
                                + math.log(r[thr_key])))
    return b


def breakeven_alpha(rows, thr_key, q=1.0, model="comb", lo=0.05, hi=1e6):
    """Smallest alpha (i.e. strongest clustering) for which the envelope
    still selects the bit-serial design at the anchor."""
    if selected_at_anchor(rows, lo, thr_key, q, model)["width"] == 1:
        return None                     # holds everywhere in the sweep
    for _ in range(100):
        mid = math.sqrt(lo * hi)
        if selected_at_anchor(rows, mid, thr_key, q, model)["width"] == 1:
            hi = mid
        else:
            lo = mid
    return math.sqrt(lo * hi)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="results/study.csv")
    ap.add_argument("--out", default="results/nb_sensitivity.md")
    args = ap.parse_args()

    rows = load_rows(args.csv)

    L = []
    w = L.append
    w("Defect-clustering sensitivity of the yield envelope\n")
    w("\nThe article's boundaries use the per-transistor Poisson model "
      "Y = exp(-dT), which\nis the zero-clustering extreme.  Clustering "
      "raises the yield of the LARGER design\nmore than that of the "
      "smaller one, so it moves every envelope boundary to a HIGHER\n"
      "defect density and SHRINKS the margin by which the 2025 anchor sits "
      "inside the\nbit-serial region.  Poisson is therefore conservative "
      "in the direction that FAVOURS\nserialization, which means it is "
      "biased towards the very answer the retrodiction\nreports -- and "
      "that makes the correction a test the retrodiction has to pass, not "
      "a\nreassurance.  This file runs that test.\n")
    w(f"\nAnchor: the published PER-TRANSISTOR functional yield "
      f"{100 * ANCHOR_YT:.2f} %.  Under (5') at\nT = 1 this gives "
      "d = alpha (Y^(-1/alpha) - 1), which equals -ln(Y) to within 0.04 % "
      "at\nalpha = 1 (0.08 % at alpha = 0.5), so the anchor does not move "
      "and only the boundaries\ndo.  That one-sidedness is what makes the "
      "sweep clean.\n")

    # ---- 1. the direct test: which width does the envelope select?
    w("\n## 1. Width selected at the published anchor\n\n")
    w("| alpha | regime | anchor d (per 10^6 T) | selected at f_max "
      "| selected at 1 kHz | Y_die of a 5,931 T chip |\n")
    w("|--:|:--|--:|:--|:--|--:|\n")
    for a in ALPHAS:
        d = anchor_d(a)
        b1 = selected_at_anchor(rows, a, "thr_fmax")
        b2 = selected_at_anchor(rows, a, "thr_1k")
        ydie = math.exp(log_yield_nb(d, T_FAB_CHIP, a))
        tag = ("Poisson (alpha -> inf)" if a > 1e5 else
               "weak clustering" if a >= 5 else
               "moderate clustering" if a >= 2 else
               "strong clustering")
        w(f"| {'inf' if a > 1e5 else f'{a:g}'} | {tag} | {d * 1e6:.0f} "
          f"| W = {b1['width']} {b1['adder']} | W = {b2['width']} "
          f"{b2['adder']} | {100 * ydie:.2f} % |\n")
    w("\nThe retrodiction is the statement that the selected width is "
      "W = 1.  The last\ncolumn is the die yield the same anchor implies "
      "for the fabricated 5,931-transistor\nchip under the same alpha, and "
      "is the independent handle on alpha: a reported die\nyield pins the "
      "row.\n")

    # ---- 2. break-even, including mapper quality
    w("\n## 2. Break-even clustering, with mapper quality\n\n")
    w("Clustering and mapper quality both push the boundaries up against a "
      "fixed anchor,\nso the worst corner is strong clustering plus a "
      "mapper better than this flow's.\nq = 1.48 is the measured "
      "transistor-count ratio of this flow to a fan-out-legalized\n"
      "yosys+ABC netlist at W = 1; q = 1.77 is the ratio to the "
      "hand-optimized fabricated\nchip.  Combinational-only scaling, since "
      "the 18-transistor flip-flop cost is fixed\nby the library.\n\n")
    w("| q | alpha* (f_max) | alpha* (1 kHz) |\n|--:|--:|--:|\n")
    for q in (1.0, 1.48, 1.77):
        vals = []
        for thr_key in ("thr_fmax", "thr_1k"):
            a_star = breakeven_alpha(rows, thr_key, q=q)
            vals.append("holds for all swept alpha" if a_star is None
                        else f"{a_star:.1f}")
        w(f"| {q:.2f} | {vals[0]} | {vals[1]} |\n")
    w("\nalpha* is the smallest clustering parameter at which the envelope "
      "still selects\nbit-serial at the anchor: the retrodiction holds "
      "for alpha > alpha* and fails below\nit.  The binding corner is the "
      "fixed 1 kHz clock with q = 1.77.\n")

    # ---- 3. ladders where they are well defined
    w("\n## 3. Boundary ladders\n\n")
    for thr_key, opname in (("thr_fmax", "f_max operation"),
                            ("thr_1k", "fixed 1 kHz clock")):
        w(f"### {opname}, q = 1\n\n")
        w("| alpha | " + " | ".join(f"switch {i}" for i in range(1, 4)) +
          " | envelope |\n|--:|--:|--:|--:|:--|\n")
        for a in ALPHAS:
            lad = ladder(rows, a, thr_key)
            ds = [d for _, d in lad if d is not None]
            cells = [f"{d * 1e6:.0f}" for d in ds[:3]]
            cells += ["--"] * (3 - len(cells))
            names = " -> ".join(n for n, _ in lad)
            w(f"| {'inf' if a > 1e5 else f'{a:g}'} | " + " | ".join(cells) +
              f" | {names} |\n")
        w("\nSwitch columns are defects per 10^6 transistors at the "
          "successive envelope\nboundaries, widest design first.  Under "
          "strong clustering the envelope loses\nwidths entirely -- the "
          "transistor-count advantage of serialization stops buying\n"
          "yield -- which is why table 1 rather than this one is the "
          "statement of the test.\n")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        f.write("".join(L))
    print("".join(L))
    print(f"\nwritten to {args.out}")


if __name__ == "__main__":
    main()
