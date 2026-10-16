"""Formal proofs for the integrated core-plus-register-file netlists
(configuration B), one point per invocation, resumable:

    python3 tools/prove_rf_system.py 1:ripple [32:prefix ...]

Same three proofs as tools/prove_flow.py (map, legalize, sub-cycle
pipeline over S periods) on the netlists of tools/rf_system.py; records go
to results/rf_formal.json.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.rf_system import CoreWithRF, POINTS                     # noqa: E402
from m2d.pdk2d import synthesize, read_mapped_json                # noqa: E402
from m2d.pdk2d.techmap import read_yosys_json, techmap            # noqa: E402
from m2d.pdk2d.pipeline import subcycle_pipeline, read_ports      # noqa: E402
from m2d.pdk2d.formal import prove_comb_equivalent, prove_subcycle  # noqa


def prove(width, adder, build="build_rf"):
    tag = f"sys_w{width}_{adder}"
    gates = os.path.join(build, f"{tag}_gates.json")
    legal = os.path.join(build, f"{tag}_mapped.json")
    if not (os.path.exists(gates) and os.path.exists(legal)):
        synthesize(CoreWithRF(width, adder), name=tag, build_dir=build,
                   verify=False)
    t0 = time.perf_counter()
    gnet = read_yosys_json(gates, top=tag)
    mapped = techmap(gnet)
    rec = {"width": width, "adder": adder,
           "map": prove_comb_equivalent(gnet, mapped)}
    lg = read_mapped_json(legal)
    rec["T_sys"] = lg.transistors()
    rec["legalize"] = prove_comb_equivalent(mapped, lg)
    ports = read_ports(gates, tag)
    pres = subcycle_pipeline(lg, ports)
    rec["S"], rec["T_sys_c"] = pres.subcycles, pres.netlist.transistors()
    rec["pipeline"] = prove_subcycle(lg, pres, ports)
    short = subcycle_pipeline(lg, ports, force_subcycles=pres.subcycles - 1)
    try:
        prove_subcycle(lg, short, ports)
        rec["minus_one_fails"] = False
    except AssertionError:
        rec["minus_one_fails"] = True
    rec["seconds"] = round(time.perf_counter() - t0, 1)
    return rec


def write_md(recs, path="results/rf_formal.md"):
    L = ["Formal proofs for the integrated core-plus-register-file netlists "
         "(configuration B; tools/prove_rf_system.py).  Columns as in "
         "results/formal.md.", "",
         "| W | adder | T_sys | outputs | map hash/SAT | legalize hash/SAT | "
         "S | T_sys,c | pipeline | S-1 fails | s |",
         "|--:|:--|--:|--:|:--|:--|--:|--:|:--:|:--:|--:|"]
    for r in recs:
        m, l = r["map"], r["legalize"]
        L.append(f"| {r['width']} | {r['adder']} | {r['T_sys']} | "
                 f"{m['outputs']} | {m['by_hashing']}/{m['by_sat']} | "
                 f"{l['by_hashing']}/{l['by_sat']} | {r['S']} | "
                 f"{r['T_sys_c']} | PROVED | "
                 f"{'yes' if r['minus_one_fails'] else 'NO'} | {r['seconds']} |")
    open(path, "w").write("\n".join(L) + "\n")


def main(argv):
    out = "results/rf_formal.json"
    recs = json.load(open(out)) if os.path.exists(out) else []
    done = {(r["width"], r["adder"]) for r in recs}
    pts = [(int(a.split(":")[0]), a.split(":")[1]) for a in argv] or POINTS
    for w, a in pts:
        if (w, a) in done:
            continue
        recs.append(prove(w, a))
        recs.sort(key=lambda r: POINTS.index((r["width"], r["adder"])))
        json.dump(recs, open(out, "w"), indent=1)
        write_md(recs)
        print("[rf-formal]", recs[-1] if recs[-1]["width"] == w else
              [r for r in recs if (r["width"], r["adder"]) == (w, a)][0],
              flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
