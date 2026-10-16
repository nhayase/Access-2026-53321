"""Scan the whole repository for depth values that predate the v6.1 fix.

Before v6.1 the analyzer reported ``2 * true_depth - 1``.  Several
checked-in outputs (README.md, build/m2d_report.txt, results/adders.md)
were written under that code and were not regenerated when it was fixed.
This script is the regression guard: it looks for any of the old values
on a line that mentions depth, stages or logic, and cross-checks
results/study.md against the current table.  Run it from the repository
root; the exit status is non-zero if anything is stale.

    python3 tools/audit_depth.py
"""
import os, re, sys

CURRENT = {          # (W, adder) -> (post-buffer, pre-buffer) depth, v6.1+
    (1, 'ripple'): (34, 29), (2, 'ripple'): (37, 30), (4, 'ripple'): (44, 35),
    (8, 'ripple'): (55, 46), (16, 'ripple'): (78, 69), (32, 'ripple'): (125, 114),
    (8, 'prefix'): (44, 35), (16, 'prefix'): (50, 39), (32, 'prefix'): (56, 41),
}
# stale = 2*true - 1
STALE = sorted({2 * v - 1 for pair in CURRENT.values() for v in pair}
               | {191, 39, 23, 13, 47, 21, 95, 31})   # standalone adders
print("stale depth values to hunt:", STALE)

# results/adders.csv carries the standalone-adder depths without the word
# "depth" on each line, so it is checked by value against results/adders.md
ADDER_DEPTH = {('4', 'ripple'): 12, ('4', 'prefix'): 7, ('8', 'ripple'): 24,
               ('8', 'prefix'): 11, ('16', 'ripple'): 48, ('16', 'prefix'): 16,
               ('32', 'ripple'): 96, ('32', 'prefix'): 20}
_csv_hits = []
if os.path.exists('results/adders.csv'):
    import csv as _csv
    for r in _csv.DictReader(open('results/adders.csv', newline='')):
        if int(r['depth']) != ADDER_DEPTH[(r['width'], r['adder'])]:
            _csv_hits.append(('results/adders.csv', r['width'], r['adder'],
                              r['depth']))

SKIP_FILES = {'CHANGES_v6.1.md', 'CHANGES_v6.2.md'}   # historical by design
SKIP_DIRS = {'.git', '__pycache__', 'figs'}
BIN_EXT = {'.png', '.svg', '.json', '.il', '.ys', '.zip', '.pyc'}

hits = []
for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
    for fn in files:
        if os.path.splitext(fn)[1] in BIN_EXT or fn in SKIP_FILES:
            continue
        p = os.path.join(root, fn)
        try:
            lines = open(p, encoding='utf-8', errors='ignore').read().splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            # only lines that look like they talk about depth/stages
            if not re.search(r'depth|stage|logic', line, re.I):
                continue
            for v in STALE:
                if re.search(rf'(?<![\d.]){v}(?![\d.])', line):
                    hits.append((p, i, v, line.strip()[:110]))
print()
if hits:
    for p, i, v, line in hits:
        print(f"  {p}:{i}  [{v}]  {line}")
    print(f"\n{len(hits)} suspicious line(s)")
else:
    print("  no stale depth value found on any depth-related line")

# positive check: every current value must appear where it should
print("\ncross-check of results/study.md against the table above:")
md = open('results/study.md', encoding='utf-8').read()
ok = True
for (w, a), (post, pre) in sorted(CURRENT.items()):
    pat = rf'\|\s*{w}\s*\|\s*{a}\s*\|.*\|\s*{post} \({pre}\)\s*\|'
    found = re.search(pat, md) is not None
    ok &= found
    print(f"  W={w:2d} {a:6s} {post:3d} ({pre:3d})  {'OK' if found else 'MISSING'}")
for h in _csv_hits:
    print("  STALE adder depth:", h)
sys.exit(0 if (ok and not hits and not _csv_hits) else 1)
