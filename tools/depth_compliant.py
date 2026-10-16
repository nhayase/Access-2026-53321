"""Depth-compliant sub-cycle pipelining of the study's design points,
one point at a time and resumable (results/depth_compliant.json holds one
record per finished point; results/depth_compliant.md is rewritten after
every point).

    python3 tools/depth_compliant.py                 # all 9 points
    python3 tools/depth_compliant.py --points 1:ripple 32:prefix
    python3 tools/depth_compliant.py --force         # redo finished points

For every point the mapped netlist of the main flow is used (synthesized
into build/ if it is not there yet), then: sub-cycle pipelining, DRC and
timing of the physical netlist, the S-period sequential equivalence check
(and the S-1 counter-check), and the gate-level execution of the checksum
workload at sub-cycle granularity (m2d/pdk2d/pipeline.py, study.py
section 10).  CPI, depth and transistor count of the unpipelined point
are taken from results/study.csv when present, otherwise re-measured.
"""
import argparse
import csv
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import study                                            # noqa: E402
from m2d.core import M2D                                # noqa: E402
from m2d.pdk2d import synthesize, read_mapped_json      # noqa: E402


def _study_rows(out_dir):
    path = os.path.join(out_dir, "study.csv")
    rows = {}
    if os.path.exists(path):
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                rows[(int(r["width"]), r["adder"])] = r
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--points", nargs="*", default=None,
                    help="W:adder pairs (default: all 9 points)")
    ap.add_argument("--build", default="build")
    ap.add_argument("-o", "--output", default="results")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-verify", action="store_true",
                    help="skip the random equivalence checks of the "
                         "main mapping flow when synthesizing")
    ap.add_argument("--patterns", type=int, default=4096)
    args = ap.parse_args(argv)

    points = study.POINTS_FULL
    if args.points:
        points = [(int(p.split(":")[0]), p.split(":")[1]) for p in args.points]
    os.makedirs(args.output, exist_ok=True)
    rec_path = os.path.join(args.output, "depth_compliant.json")
    recs = []
    if os.path.exists(rec_path):
        with open(rec_path) as f:
            recs = json.load(f)
    done = {(r["width"], r["adder"]): r for r in recs}
    table = _study_rows(args.output)
    goldens = None

    for width, adder in points:
        if (width, adder) in done and not args.force:
            print(f"[dc] W={width} {adder}: already done "
                  f"(S = {done[(width, adder)]['S']})")
            continue
        tag = f"m2d_w{width}_{adder}"
        t0 = time.perf_counter()
        mapped_path = os.path.join(args.build, f"{tag}_mapped.json")
        if not os.path.exists(mapped_path):
            print(f"[dc] synthesizing {tag} ...")
            flow = synthesize(M2D(width=width, adder=adder), name=tag,
                              build_dir=args.build,
                              verify=not args.no_verify)
            mapped = flow.mapped
            depth = flow.result.logic_depth
            transistors = flow.result.transistors
        else:
            mapped = read_mapped_json(mapped_path)
            from m2d.pdk2d import analyze
            res = analyze(mapped)
            depth, transistors = res.logic_depth, res.transistors
        row = table.get((width, adder))
        if row is not None:
            cpi = float(row["cpi_geo"])
            if int(row["depth"]) != depth or \
                    int(row["transistors"]) != transistors:
                print(f"[dc] WARNING: build/ netlist differs from "
                      f"results/study.csv for {tag} (depth {depth} vs "
                      f"{row['depth']}, T {transistors} vs "
                      f"{row['transistors']})")
        else:
            if goldens is None:
                goldens = study.load_goldens()
            cpi = study.measure_workloads(width, adder, goldens)["geomean"]
        rec = study.depth_compliant_point(mapped, width, adder, cpi, depth,
                                          transistors, build_dir=args.build,
                                          patterns=args.patterns)
        rec["seconds"] = round(time.perf_counter() - t0, 1)
        done[(width, adder)] = rec
        recs = [done[k] for k in sorted(done, key=lambda k: (k[1] != "ripple",
                                                              k[0]))]
        with open(rec_path, "w") as f:
            json.dump(recs, f, indent=1)
        print(f"[dc] W={width} {adder}: S = {rec['S']} "
              f"(analytic {rec['S_analytic']}), T_c = {rec['T_c']} "
              f"(analytic {rec['T_analytic']}), depth {rec['depth_c']} "
              f"{'PASS' if rec['depth_ok'] else 'FAIL'}, seq. equiv. "
              f"{rec['seq_equiv_patterns']} cases, S-1 fails: "
              f"{rec['minus_one_fails']}, gate-level {rec['gate_arch_cycles']}"
              f" arch cycles (RTL {rec['rtl_cycles']}), "
              f"{rec['seconds']} s")
        study.write_depth_compliant_md(recs, args.output)
    if recs:
        print(f"[dc] {study.write_depth_compliant_md(recs, args.output)} "
              f"written ({len(recs)} points)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
