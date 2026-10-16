#!/usr/bin/env python3
"""Build only the RTLIL + mapped netlists needed by the ABC cross-check."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from m2d.core import M2D
from m2d.pdk2d.synth import synthesize

POINTS = [(1, "ripple"), (32, "ripple"), (32, "prefix")]

for w, a in POINTS:
    tag = f"m2d_w{w}_{a}"
    print(f"=== {tag} ===")
    flow = synthesize(M2D(width=w, adder=a), name=tag, build_dir="build")
    r = flow.result
    print(f"{tag}: post-buf cells={sum(r.cell_counts.values())} "
          f"T={r.transistors} depth={r.logic_depth} "
          f"| pre-buf cells={sum(flow.prebuffer.cell_counts.values())} "
          f"T={flow.prebuffer.transistors} depth={flow.prebuffer.logic_depth}")
