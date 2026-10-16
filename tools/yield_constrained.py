#!/usr/bin/env python3
"""Width selection under a minimum die-yield constraint (Poisson), exactly.

For every configuration (A: register file off the die, B: on the die),
reading of the 17-stage rule, clock and metric, the selection

    maximize  thr_i exp(-d T_i)      (per die)   or  .../T_i  (per area)
    subject to  exp(-d T_i) >= Y_min                     (Y_min = 10 %)

is solved piecewise in the defect density d: the breakpoints are all
pairwise boundaries d*_ij of (15) and all feasibility limits ln(1/Y_min)/T_i,
and the selection is evaluated inside every interval between consecutive
breakpoints.  The unconstrained ladder (Y_min = 0) is reported alongside.

Writes results/yield_constrained.md and results/yield_constrained.json.
"""
import csv
import json
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POINTS = [(1, "ripple"), (2, "ripple"), (4, "ripple"), (8, "ripple"),
          (16, "ripple"), (32, "ripple"), (8, "prefix"), (16, "prefix"),
          (32, "prefix")]
F_C = 5847.3


def short(w, a):
    return f"{w}{'r' if a == 'ripple' else 'BK'}" if w > 1 else "1"


def designs():
    core = {(int(r["width"]), r["adder"]): r for r in
            csv.DictReader(open(os.path.join(ROOT, "results/study.csv")))}
    comp = {(r["width"], r["adder"]): r for r in
            json.load(open(os.path.join(ROOT, "results/depth_compliant.json")))}
    rs = json.load(open(os.path.join(ROOT, "results/rf_system.json")))
    sysr = {(r["width"], r["adder"]): r for r in rs if r["what"] == "system"}
    pipe = {(r["width"], r["adder"]): r for r in json.load(
        open(os.path.join(ROOT, "results/rf_system_pipelined.json")))}
    out = {}
    for w, a in POINTS:
        c = core[(w, a)]
        cpi = float(c["cpi_geomean"])
        k = short(w, a)
        out.setdefault(("A", "delay budget", "1 kHz"), {})[k] = (
            int(c["transistors"]), 1000.0 / cpi)
        out.setdefault(("A", "delay budget", "f_max"), {})[k] = (
            int(c["transistors"]), float(c["fmax_hz"]) / cpi)
        p = comp[(w, a)]
        out.setdefault(("A", "cascade", "f_c"), {})[k] = (
            p["T_c"], F_C / (cpi * p["S"]))
        s, q = sysr[(w, a)], pipe[(w, a)]
        out.setdefault(("B", "delay budget", "1 kHz"), {})[k] = (
            s["transistors"], 1000.0 / cpi)
        out.setdefault(("B", "delay budget", "f_max"), {})[k] = (
            s["transistors"], 1e6 / s["delay_us"] / cpi)
        out.setdefault(("B", "cascade", "f_c"), {})[k] = (
            q["T_c"], F_C / (cpi * q["S"]))
    return out


def score(T, thr, d, area):
    v = math.log(thr) - d * T
    return v - math.log(T) if area else v


def ladder(ds, area, ymin):
    """[(design or None, d_low, d_high)] over d in [0, inf), d in per-T."""
    lim = math.log(1.0 / ymin) if ymin > 0 else None
    bps = {0.0}
    keys = list(ds)
    for i, a in enumerate(keys):
        Ta, ta = ds[a]
        if lim is not None:
            bps.add(lim / Ta)
        for b in keys[i + 1:]:
            Tb, tb = ds[b]
            if Ta == Tb:
                continue
            num = math.log(ta / tb) - (math.log(Ta / Tb) if area else 0.0)
            x = num / (Ta - Tb)
            if x > 0:
                bps.add(x)
    bps = sorted(bps) + [1.0]
    segs = []
    for lo, hi in zip(bps[:-1], bps[1:]):
        d = 0.5 * (lo + hi)
        feas = [k for k in keys if lim is None or d * ds[k][0] <= lim]
        best = max(feas, key=lambda k: score(*ds[k], d, area)) if feas else None
        if segs and segs[-1][0] == best:
            segs[-1][2] = hi
        else:
            segs.append([best, lo, hi])
    return segs


def fmt(segs):
    parts = []
    for k, lo, hi in segs:
        name = k if k is not None else "none"
        hi_s = "∞" if hi >= 1.0 else f"{hi * 1e6:,.1f}"
        parts.append(f"{name} [{lo * 1e6:,.1f}, {hi_s})")
    return "; ".join(parts)


def serial_window(segs):
    return [(lo * 1e6, hi * 1e6) for k, lo, hi in segs if k == "1"]


def main():
    ds = designs()
    res = []
    L = ["Width selection with and without a 10 % die-yield constraint "
         "(Poisson; tools/yield_constrained.py).  Intervals in ppm/T; "
         "'none': no design meets the constraint.", ""]
    for (cfg, reading, clk), d in ds.items():
        for area in (False, True):
            u = ladder(d, area, 0.0)
            c = ladder(d, area, 0.10)
            rec = dict(config=cfg, reading=reading, clock=clk,
                       metric="area" if area else "die",
                       unconstrained=[(k, lo * 1e6, hi * 1e6) for k, lo, hi in u],
                       constrained=[(k, lo * 1e6, hi * 1e6) for k, lo, hi in c],
                       serial_unconstrained=serial_window(u),
                       serial_constrained=serial_window(c))
            res.append(rec)
            L += [f"## {cfg}, {reading}, {clk}, per {rec['metric']}",
                  f"unconstrained: {fmt(u)}", f"Y >= 10 %:     {fmt(c)}", ""]
    json.dump(res, open(os.path.join(ROOT, "results/yield_constrained.json"),
                        "w"), indent=1)
    open(os.path.join(ROOT, "results/yield_constrained.md"), "w").write(
        "\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
