QoR sensitivity of the defect-density ladder

The boundary d* = ln(thr_i/thr_j)/(T_i - T_j) depends on a DIFFERENCE of
transistor counts, so the mapper's QoR overhead does NOT cancel from it, as it
does from every serial-to-parallel ratio.   For a mapper q times BETTER than this
flow, T -> T/q and the boundary scales exactly as d*(q) = q d*(1), so the ladder
rises with q and the exit yields relax.  q is
measured between fan-out-legalized netlists on both sides (see the module
docstring); it is no longer an upper bound.

## uniform inflation T' = T/q, f_max operation

| q | switch 1 | switch 2 | switch 3 | exit yields (per transistor) | margin to the 2025 anchor |
|--:|--:|--:|--:|:--|:--|
| 1.00  (as reported (this flow)) | 41 | 92 | 198 | 99.996 % / 99.991 % / 99.980 % | x4.0 |
| 1.25 | 51 | 116 | 248 | 99.995 % / 99.988 % / 99.975 % | x3.2 |
| 1.48  (measured vs. legalized yosys+ABC) | 60 | 137 | 293 | 99.994 % / 99.986 % / 99.971 % | x2.7 |
| 1.60 | 65 | 148 | 317 | 99.994 % / 99.985 % / 99.968 % | x2.5 |
| 1.77  (measured vs. hand-optimized chip at W = 1) | 72 | 164 | 351 | 99.993 % / 99.984 % / 99.965 % | x2.3 |
| 2.00 | 81 | 185 | 396 | 99.992 % / 99.982 % / 99.960 % | x2.0 |

Switch columns are defects per 10^6 transistors at the successive envelope
boundaries (widest first).  The margin column is the ratio of the published
per-transistor anchor (800 defects per 10^6 T) to the last boundary, i.e. how
far inside the bit-serial region the 2025 process still sits.

## uniform inflation T' = T/q, fixed 1 kHz clock

| q | switch 1 | switch 2 | switch 3 | exit yields (per transistor) | margin to the 2025 anchor |
|--:|--:|--:|--:|:--|:--|
| 1.00  (as reported (this flow)) | 67 | 156 | 249 | 99.993 % / 99.984 % / 99.975 % | x3.2 |
| 1.25 | 84 | 195 | 312 | 99.992 % / 99.981 % / 99.969 % | x2.6 |
| 1.48  (measured vs. legalized yosys+ABC) | 100 | 231 | 369 | 99.990 % / 99.977 % / 99.963 % | x2.2 |
| 1.60 | 108 | 250 | 399 | 99.989 % / 99.975 % / 99.960 % | x2.0 |
| 1.77  (measured vs. hand-optimized chip at W = 1) | 119 | 276 | 441 | 99.988 % / 99.972 % / 99.956 % | x1.8 |
| 2.00 | 135 | 312 | 498 | 99.987 % / 99.969 % / 99.950 % | x1.6 |

Switch columns are defects per 10^6 transistors at the successive envelope
boundaries (widest first).  The margin column is the ratio of the published
per-transistor anchor (800 defects per 10^6 T) to the last boundary, i.e. how
far inside the bit-serial region the 2025 process still sits.

## combinational-only T' = T_ff + (T - T_ff)/q, f_max operation

| q | switch 1 | switch 2 | switch 3 | exit yields (per transistor) | margin to the 2025 anchor |
|--:|--:|--:|--:|:--|:--|
| 1.00  (as reported (this flow)) | 41 | 92 | 198 | 99.996 % / 99.991 % / 99.980 % | x4.0 |
| 1.25 | 51 | 116 | 249 | 99.995 % / 99.988 % / 99.975 % | x3.2 |
| 1.48  (measured vs. legalized yosys+ABC) | 60 | 137 | 296 | 99.994 % / 99.986 % / 99.970 % | x2.7 |
| 1.60 | 65 | 148 | 321 | 99.994 % / 99.985 % / 99.968 % | x2.5 |
| 1.77  (measured vs. hand-optimized chip at W = 1) | 72 | 164 | 356 | 99.993 % / 99.984 % / 99.964 % | x2.2 |
| 2.00 | 81 | 186 | 404 | 99.992 % / 99.981 % / 99.960 % | x2.0 |

Switch columns are defects per 10^6 transistors at the successive envelope
boundaries (widest first).  The margin column is the ratio of the published
per-transistor anchor (800 defects per 10^6 T) to the last boundary, i.e. how
far inside the bit-serial region the 2025 process still sits.

## combinational-only T' = T_ff + (T - T_ff)/q, fixed 1 kHz clock

| q | switch 1 | switch 2 | switch 3 | exit yields (per transistor) | margin to the 2025 anchor |
|--:|--:|--:|--:|:--|:--|
| 1.00  (as reported (this flow)) | 67 | 156 | 249 | 99.993 % / 99.984 % / 99.975 % | x3.2 |
| 1.25 | 84 | 195 | 313 | 99.992 % / 99.980 % / 99.969 % | x2.6 |
| 1.48  (measured vs. legalized yosys+ABC) | 100 | 232 | 372 | 99.990 % / 99.977 % / 99.963 % | x2.1 |
| 1.60 | 108 | 251 | 404 | 99.989 % / 99.975 % / 99.960 % | x2.0 |
| 1.77  (measured vs. hand-optimized chip at W = 1) | 119 | 277 | 448 | 99.988 % / 99.972 % / 99.955 % | x1.8 |
| 2.00 | 135 | 314 | 508 | 99.986 % / 99.969 % / 99.949 % | x1.6 |

Switch columns are defects per 10^6 transistors at the successive envelope
boundaries (widest first).  The margin column is the ratio of the published
per-transistor anchor (800 defects per 10^6 T) to the last boundary, i.e. how
far inside the bit-serial region the 2025 process still sits.

## Reading

Under the Poisson model the retrodiction is mapper-independent: across every q
considered, and under both scaling models, the published per-transistor anchor
remains strictly inside the bit-serial region, so the conclusion that the map
selects the width that was in fact built does not depend on the mapper.  What
DOES depend on the mapper is the QUANTITATIVE exit threshold: the values quoted
in the article are computed at q = 1, i.e. with this flow's own transistor counts,
and a better mapper moves them upward in defect density and downward in required
yield.  The article therefore quotes the exit yields with their q dependence stated
rather than to five significant figures as if they were mapper-independent.

The mapper axis is NOT the binding one, however.  Defect clustering moves the
same boundaries in the same direction and by considerably more; see
results/nb_sensitivity.md, which sweeps it and reports the break-even.
