"""Formal (SAT) proofs of the synthesis flow, one design point at a time
and resumable (results/formal.json holds one record per finished point;
results/formal.md is rewritten after every point).

    python3 tools/prove_flow.py                       # all 9 points
    python3 tools/prove_flow.py --points 1:ripple 32:prefix
    python3 tools/prove_flow.py --force

Per point (m2d/pdk2d/formal.py):
  1. primitive netlist (yosys)  == mapped netlist (technology mapping)
  2. mapped netlist             == fan-out-legalized netlist (the one the
                                   study analyzes, build/<tag>_mapped.json)
  3. legalized netlist (1 eval) == depth-compliant physical netlist over S
                                   periods (all states, all pipeline
                                   contents, all environment garbage)
  4. negative controls: the same physical netlist with a ring of S - 1
     phases must fail proof 3, and 20 random single-cell mutants of the
     mapped netlist must each fail proof 1.
"""
import argparse
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from m2d.core import M2D                                        # noqa: E402
from m2d.pdk2d import synthesize, read_mapped_json             # noqa: E402
from m2d.pdk2d.techmap import read_yosys_json, techmap         # noqa: E402
from m2d.pdk2d.pipeline import subcycle_pipeline, read_ports   # noqa: E402
from m2d.pdk2d.formal import prove_comb_equivalent, prove_subcycle  # noqa

POINTS = [(1, "ripple"), (2, "ripple"), (4, "ripple"), (8, "ripple"),
          (16, "ripple"), (32, "ripple"), (8, "prefix"), (16, "prefix"),
          (32, "prefix")]

_SWAP = {"NAND2": "NOR2", "NOR2": "NAND2", "AND2": "OR2", "OR2": "AND2",
         "AOI21": "OAI21", "OAI21": "AOI21", "AOI22": "OAI22",
         "OAI22": "AOI22", "XOR2": "NAND2", "NAND3": "NOR3", "NOR3": "NAND3"}


def _mutants_detected(gnet, mapped, n=20, seed=1):
    rnd = random.Random(seed)
    gids = [k for k, v in mapped.gates.items() if v[0] in _SWAP]
    hit = 0
    for _ in range(n):
        mm = mapped.copy()
        k = rnd.choice(gids)
        mm.gates[k][0] = _SWAP[mm.gates[k][0]]
        try:
            prove_comb_equivalent(gnet, mm)
        except AssertionError:
            hit += 1
    return hit, n


def prove_point(width, adder, build):
    tag = f"m2d_w{width}_{adder}"
    gates = os.path.join(build, f"{tag}_gates.json")
    legal = os.path.join(build, f"{tag}_mapped.json")
    if not (os.path.exists(gates) and os.path.exists(legal)):
        synthesize(M2D(width=width, adder=adder), name=tag, build_dir=build,
                   verify=False)
    rec = {"width": width, "adder": adder}
    t0 = time.perf_counter()
    gnet = read_yosys_json(gates, top=tag)
    mapped = techmap(gnet)
    st = prove_comb_equivalent(gnet, mapped)
    rec["map"] = st
    legalized = read_mapped_json(legal)
    rec["T"] = legalized.transistors()
    rec["legalize"] = prove_comb_equivalent(mapped, legalized)
    ports = read_ports(gates, tag)
    pres = subcycle_pipeline(legalized, ports)
    rec["S"] = pres.subcycles
    rec["T_c"] = pres.netlist.transistors()
    rec["pipeline"] = prove_subcycle(legalized, pres, ports)
    short = subcycle_pipeline(legalized, ports,
                              force_subcycles=pres.subcycles - 1)
    try:
        prove_subcycle(legalized, short, ports)
        rec["minus_one_fails"] = False
    except AssertionError:
        rec["minus_one_fails"] = True
    rec["mutants_detected"] = list(_mutants_detected(gnet, mapped))
    rec["seconds"] = round(time.perf_counter() - t0, 1)
    return rec


def write_md(recs, out):
    lines = [
        "Formal equivalence proofs of the synthesis flow (m2d/pdk2d/formal.py,"
        " tools/prove_flow.py).",
        "",
        "map: primitive (yosys) == mapped; legalize: mapped == fan-out-"
        "legalized; pipeline: legalized (one evaluation) == depth-compliant "
        "physical netlist over S periods for all architectural states, "
        "pipeline contents and environment garbage.  'hash' = outputs whose "
        "AIG literals coincide after structural hashing, 'SAT' = outputs "
        "proved by CaDiCaL.  Negative controls: the S - 1 ring must fail "
        "the pipeline proof; random single-cell mutants must fail the map "
        "proof.",
        "",
        "| W | adder | T | outputs | map hash/SAT | legalize hash/SAT | S | "
        "T_c | pipeline | S-1 fails | mutants detected | s |",
        "|--:|:--|--:|--:|:--|:--|--:|--:|:--:|:--:|:--:|--:|",
    ]
    for r in recs:
        m, l = r["map"], r["legalize"]
        lines.append(
            f"| {r['width']} | {r['adder']} | {r['T']} | {m['outputs']} | "
            f"{m['by_hashing']}/{m['by_sat']} | {l['by_hashing']}/"
            f"{l['by_sat']} | {r['S']} | {r['T_c']} | PROVED | "
            f"{'yes' if r['minus_one_fails'] else 'NO'} | "
            f"{r['mutants_detected'][0]}/{r['mutants_detected'][1]} | "
            f"{r['seconds']} |")
    path = os.path.join(out, "formal.md")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return path


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--points", nargs="*", default=None)
    ap.add_argument("--build", default="build")
    ap.add_argument("-o", "--output", default="results")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    points = POINTS
    if args.points:
        points = [(int(p.split(":")[0]), p.split(":")[1]) for p in args.points]
    rec_path = os.path.join(args.output, "formal.json")
    recs = []
    if os.path.exists(rec_path):
        with open(rec_path) as f:
            recs = json.load(f)
    done = {(r["width"], r["adder"]): r for r in recs}
    for w, a in points:
        if (w, a) in done and not args.force:
            print(f"[formal] W={w} {a}: already proved")
            continue
        rec = prove_point(w, a, args.build)
        done[(w, a)] = rec
        recs = [done[k] for k in POINTS if k in done]
        with open(rec_path, "w") as f:
            json.dump(recs, f, indent=1)
        write_md(recs, args.output)
        print(f"[formal] W={w} {a}: map {rec['map']}, legalize "
              f"{rec['legalize']}, S={rec['S']} pipeline {rec['pipeline']}, "
              f"S-1 fails {rec['minus_one_fails']}, mutants "
              f"{rec['mutants_detected']}, {rec['seconds']} s")
    if recs:
        print(f"[formal] {write_md(recs, args.output)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
