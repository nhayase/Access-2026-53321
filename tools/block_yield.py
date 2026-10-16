#!/usr/bin/env python3
"""Defect density and clustering fixed by the yield data of [1]
(Ao et al., Nature 640, 654-661 (2025)); writes results/block_yield.md,
results/block_yield.json and paper/fig4_block_yield.png.

Published figures used (source in brackets):
  per-transistor functional yield 99.92 %                    [1, main text]
  inverters: 898 of 900 functional (30 x 30 array)           [1, main text;
                                                              Suppl. Fig. 4]
  8-bit shift registers (144 T): 71 % of 224                 [1, Suppl. Fig. 7]
  64-bit registers (1,152 T = 8 x 144 T): 7 %                [1, main text];
      the wafer of Suppl. Fig. 7 holds 28 such matrices, so 7 % is 2 of 28.

The two register figures come from the same wafer and differ only in size
(1,152 T is eight of the 144-T blocks), so together they fix both
parameters of the negative-binomial model Y(T) = (1 + d T / alpha)^-alpha
(alpha -> infinity is Poisson).  Fit: binomial maximum likelihood on
159/224 and 2/28 (the integer counts nearest to the published percentages),
95 % intervals from the profile likelihood (chi^2_1 = 3.84); treating the
nested counts as independent is an approximation that widens nothing.
The fitted (d, alpha) are then put into the per-die envelope of the study
(Tables II/V: delay-budget reading; IX: cascade reading).
"""
import csv
import json
import math
import os
import sys

import numpy as np
from scipy import optimize, stats

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA = [  # label, T per unit, functional, tested (None: count unpublished)
    ("transistor", 1, 0.9992, None),
    ("inverter", 2, 898, 900),
    ("8-bit register", 144, 159, 224),
    ("64-bit register", 1152, 2, 28),
]
T_WUJI = 5931


def cp(k, n, a=0.05):
    lo = 0.0 if k == 0 else stats.beta.ppf(a / 2, k, n - k + 1)
    hi = 1.0 if k == n else stats.beta.ppf(1 - a / 2, k + 1, n - k)
    return lo, hi


def logy(d, T, alpha):
    return -d * T if alpha > 1e7 else -alpha * math.log1p(d * T / alpha)


def nll(d, alpha, pts):
    s = 0.0
    for T, k, n in pts:
        ly = logy(d, T, alpha)
        y = math.exp(ly)
        s -= k * ly + (n - k) * math.log(max(1.0 - y, 1e-300))
    return s


def fit(pts):
    best = None
    for la in np.linspace(-1, 7, 161):          # log10 alpha grid
        a = 10 ** la
        r = optimize.minimize_scalar(lambda ld: nll(10 ** ld, a, pts),
                                     bounds=(-5, -1), method="bounded")
        if best is None or r.fun < best[0]:
            best = (r.fun, 10 ** r.x, a)
    r = optimize.minimize(lambda v: nll(10 ** v[0], 10 ** v[1], pts),
                          [math.log10(best[1]), math.log10(best[2])],
                          method="Nelder-Mead",
                          options={"xatol": 1e-6, "fatol": 1e-9})
    return r.fun, 10 ** r.x[0], 10 ** r.x[1]


def profile_alpha(pts, f0):
    out = []
    for la in np.linspace(-1, 7, 321):
        a = 10 ** la
        r = optimize.minimize_scalar(lambda ld: nll(10 ** ld, a, pts),
                                     bounds=(-5, -1), method="bounded")
        out.append((a, r.fun - f0, 10 ** r.x))
    return out


def profile_d(pts, f0):
    out = []
    for ld in np.linspace(math.log10(800e-6), math.log10(5000e-6), 241):
        d = 10 ** ld
        r = optimize.minimize_scalar(lambda la: nll(d, 10 ** la, pts),
                                     bounds=(-1, 7), method="bounded")
        out.append((d, r.fun - f0))
    return out


def designs():
    rows = list(csv.DictReader(open(os.path.join(ROOT, "results/study.csv"))))
    dc = json.load(open(os.path.join(ROOT, "results/depth_compliant.json")))
    A1k = {f"W={r['width']} {r['adder']}": (int(r["transistors"]),
                                           1000.0 / float(r["cpi_geomean"]))
           for r in rows}
    Afm = {f"W={r['width']} {r['adder']}": (int(r["transistors"]),
                                           float(r["thr_fmax"])) for r in rows}
    C = {f"W={r['width']} {r['adder']}": (r["T_c"], r["thr_c"]) for r in dc}
    return {"delay budget, 1 kHz": A1k, "delay budget, fmax": Afm,
            "cascade": C}


def select(ds, d, alpha):
    return max(ds, key=lambda k: math.log(ds[k][1]) + logy(d, ds[k][0], alpha))


def main():
    pts = [(T, k, n) for _, T, k, n in DATA[2:]]
    f0, d_hat, a_hat = fit(pts)
    prof = profile_alpha(pts, f0)
    inside = [a for a, dl, _ in prof if dl <= 3.8415 / 2]
    a_lo = min(inside)
    a_hi = max(inside)
    a_hi_open = a_hi >= 0.99e7
    pd = profile_d(pts, f0)
    din = [d for d, dl in pd if dl <= 3.8415 / 2]
    d_lo, d_hi = min(din), max(din)
    # Poisson-only fit of the two registers
    rp = optimize.minimize_scalar(lambda ld: nll(10 ** ld, 1e8, pts),
                                  bounds=(-5, -1), method="bounded")
    d_pois = 10 ** rp.x
    lr_pois = 2 * (rp.fun - f0)

    rows = []
    for label, T, k, n in DATA:
        if n is None:
            y, lo, hi = k, None, None
            dp, dlo, dhi = -math.log(k), None, None
        else:
            y = k / n
            lo, hi = cp(k, n)
            dp = -math.log(y) / T
            dlo, dhi = -math.log(hi) / T, -math.log(lo) / T
        rows.append(dict(label=label, T=T, k=k, n=n, Y=y, Y_lo=lo, Y_hi=hi,
                         d_ppm=dp * 1e6,
                         d_lo_ppm=None if dlo is None else dlo * 1e6,
                         d_hi_ppm=None if dhi is None else dhi * 1e6))

    # profile-likelihood p-value of the break-even clustering parameters of
    # Table XIII (alpha below alpha* would overturn the consistency check)
    alpha_star = {"delay budget, 1 kHz, die": 5.0, "delay budget, fmax, die":
                  3.7, "delay budget, 1 kHz, area": 3.1, "cascade, die": 2.1,
                  "cascade, area": 0.9}
    p_star = {}
    for k, a in alpha_star.items():
        r = optimize.minimize_scalar(lambda ld: nll(10 ** ld, a, pts),
                                     bounds=(-5, -1), method="bounded")
        p_star[k] = dict(alpha_star=a, p=float(stats.chi2.sf(
            max(2 * (r.fun - f0), 0), 1)))

    ds = designs()
    sel = {}
    grid = [("fit", d_hat, a_hat), ("alpha lower 95 %", None, a_lo)]
    for name, d, a in grid:
        if d is None:   # profile-optimal d at the lower alpha bound
            d = min(prof, key=lambda t: abs(math.log(t[0] / a)))[2]
        sel[name] = dict(d_ppm=d * 1e6, alpha=a,
                         **{k: select(v, d, a) for k, v in ds.items()})
    # selection at the transistor anchor (800 ppm/T) with the fitted alpha
    sel["800 ppm/T, fitted alpha"] = dict(
        d_ppm=800.0, alpha=a_hat,
        **{k: select(v, 800e-6, a_hat) for k, v in ds.items()})
    yd = {T: math.exp(logy(d_hat, T, a_hat))
          for T in (T_WUJI, 10474, 15500, 27195)}

    res = dict(data=rows, d_hat_ppm=d_hat * 1e6, alpha_hat=a_hat,
               alpha_ci=[a_lo, None if a_hi_open else a_hi],
               d_ci_ppm=[d_lo * 1e6, d_hi * 1e6], d_poisson_ppm=d_pois * 1e6,
               lr_poisson=lr_pois, p_poisson=float(stats.chi2.sf(max(lr_pois, 0), 1)),
               p_alpha_star=p_star, selection=sel, die_yield_fit={str(k): v for k, v in yd.items()})
    json.dump(res, open(os.path.join(ROOT, "results/block_yield.json"), "w"),
              indent=1)

    L = ["Defect density and clustering fixed by the yield data of [1] "
         "(tools/block_yield.py)", "",
         "| structure | T | functional | yield | 95 % CI | Poisson d "
         "(ppm/T) | 95 % CI |", "|:--|--:|--:|--:|:--|--:|:--|"]
    for r in rows:
        if r["n"] is None:
            L.append(f"| {r['label']} | 1 | n/a | {100*r['Y']:.2f} % | -- | "
                     f"{r['d_ppm']:.0f} | -- |")
        else:
            L.append(f"| {r['label']} | {r['T']} | {r['k']}/{r['n']} | "
                     f"{100*r['Y']:.2f} % | {100*r['Y_lo']:.2f}-"
                     f"{100*r['Y_hi']:.2f} % | {r['d_ppm']:.0f} | "
                     f"{r['d_lo_ppm']:.0f}-{r['d_hi_ppm']:.0f} |")
    L += ["", f"Negative-binomial fit to the two register sizes: d = "
          f"{d_hat*1e6:.0f} ppm/T (95 % {d_lo*1e6:.0f}-{d_hi*1e6:.0f}), "
          f"alpha = {a_hat:.0f} (95 % lower bound {a_lo:.1f}, upper "
          f"{'unbounded' if a_hi_open else f'{a_hi:.0f}'}).  Poisson-only "
          f"fit: d = {d_pois*1e6:.0f} ppm/T, likelihood-ratio statistic "
          f"{lr_pois:.3f} (p = {res['p_poisson']:.2f}): the data do not "
          "distinguish clustering from Poisson.", "",
          "Profile-likelihood p-value of each break-even alpha* (Table XIII): "
          + ", ".join(f"{k} (alpha* = {v['alpha_star']}): p = {v['p']:.2f}"
                      for k, v in p_star.items()), "",
          "Per-die envelope selection under the fitted parameters:", "",
          "| point | d (ppm/T) | alpha | delay budget, 1 kHz | delay budget, "
          "fmax | cascade |", "|:--|--:|--:|:--|:--|:--|"]
    for name, s in sel.items():
        L.append(f"| {name} | {s['d_ppm']:.0f} | {s['alpha']:.1f} | "
                 f"{s['delay budget, 1 kHz']} | {s['delay budget, fmax']} | "
                 f"{s['cascade']} |")
    L += ["", "Die yield under the fitted model: " + ", ".join(
        f"{k} T: {v:.1e}" for k, v in yd.items())]
    open(os.path.join(ROOT, "results/block_yield.md"), "w").write(
        "\n".join(L) + "\n")
    print("\n".join(L))
    if "--fig" in sys.argv:
        figure(rows, d_hat, a_hat, sel["alpha lower 95 %"])


def figure(rows, d_hat, a_hat, lo):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    T = np.logspace(0, 4.7, 400)
    fig, ax = plt.subplots(figsize=(3.5, 2.75))
    ax.plot(T, np.exp(-800e-6 * T), "r--", lw=1.0,
            label="Poisson, 800 ppm/T (99.92 % per T)")
    ax.plot(T, (1 + d_hat * T / a_hat) ** (-a_hat), "k-", lw=1.4,
            label=f"NB fit to registers: {d_hat*1e6:.0f} ppm/T, "
                  f"$\\alpha$ = {a_hat:.0f}")
    dl, al = lo["d_ppm"] * 1e-6, lo["alpha"]
    ax.plot(T, (1 + dl * T / al) ** (-al), color="0.45", ls="-.", lw=0.9,
            label=f"NB, $\\alpha$ = {al:.1f} (95 % lower bound)")
    for r, m in zip(rows, ("s", "^", "o", "o")):
        if r["n"] is None:
            ax.plot(r["T"], r["Y"], "r" + m, ms=5)
            continue
        ax.errorbar(r["T"], r["Y"], yerr=[[r["Y"] - r["Y_lo"]],
                                          [r["Y_hi"] - r["Y"]]],
                    fmt="k" + m, ms=4, capsize=2, lw=0.8)
    for r, txt, dx, dy in ((rows[1], "inverters", 1.4, 0.55),
                           (rows[2], "8-bit reg.", 1.3, 1.25),
                           (rows[3], "64-bit reg.", 1.3, 1.6)):
        ax.text(r["T"] * dx, r["Y"] * dy, txt, fontsize=5.5, va="center")
    for Tm, lab in ((T_WUJI, "WUJI"), (10474, "W=1"), (27195, "W=32")):
        ax.axvline(Tm, color="0.6", lw=0.6, ls=":")
        ax.text(Tm * 0.93, 0.4, lab, rotation=90, fontsize=6, ha="right",
                va="top", color="0.35")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_ylim(1e-5, 1.5)
    ax.set_xlim(0.7, 5e4)
    ax.set_xlabel("transistors per functional unit $T$", fontsize=7)
    ax.set_ylabel("yield", fontsize=7)
    ax.tick_params(labelsize=6)
    ax.grid(True, which="major", lw=0.3, alpha=0.5)
    ax.legend(fontsize=5.5, loc="lower left", frameon=False)
    fig.tight_layout(pad=0.3)
    fig.savefig(os.path.join(ROOT, "paper/fig4_block_yield.png"), dpi=600)


if __name__ == "__main__":
    main()
