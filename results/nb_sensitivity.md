Defect-clustering sensitivity of the yield envelope

The article's boundaries use the per-transistor Poisson model Y = exp(-dT), which
is the zero-clustering extreme.  Clustering raises the yield of the LARGER design
more than that of the smaller one, so it moves every envelope boundary to a HIGHER
defect density and SHRINKS the margin by which the 2025 anchor sits inside the
bit-serial region.  Poisson is therefore conservative in the direction that FAVOURS
serialization, which means it is biased towards the very answer the retrodiction
reports -- and that makes the correction a test the retrodiction has to pass, not a
reassurance.  This file runs that test.

Anchor: the published PER-TRANSISTOR functional yield 99.92 %.  Under (5') at
T = 1 this gives d = alpha (Y^(-1/alpha) - 1), which equals -ln(Y) to within 0.04 % at
alpha = 1 (0.08 % at alpha = 0.5), so the anchor does not move and only the boundaries
do.  That one-sidedness is what makes the sweep clean.

## 1. Width selected at the published anchor

| alpha | regime | anchor d (per 10^6 T) | selected at f_max | selected at 1 kHz | Y_die of a 5,931 T chip |
|--:|:--|--:|:--|:--|--:|
| inf | Poisson (alpha -> inf) | 800 | W = 1 ripple | W = 1 ripple | 0.87 % |
| 10 | weak clustering | 800 | W = 1 ripple | W = 1 ripple | 2.06 % |
| 5 | weak clustering | 800 | W = 1 ripple | W = 8 ripple | 3.55 % |
| 3 | moderate clustering | 800 | W = 8 prefix | W = 16 ripple | 5.81 % |
| 2 | moderate clustering | 800 | W = 16 prefix | W = 16 ripple | 8.79 % |
| 1 | strong clustering | 801 | W = 32 prefix | W = 32 ripple | 17.40 % |
| 0.5 | strong clustering | 801 | W = 32 prefix | W = 32 ripple | 30.86 % |

The retrodiction is the statement that the selected width is W = 1.  The last
column is the die yield the same anchor implies for the fabricated 5,931-transistor
chip under the same alpha, and is the independent handle on alpha: a reported die
yield pins the row.

## 2. Break-even clustering, with mapper quality

Clustering and mapper quality both push the boundaries up against a fixed anchor,
so the worst corner is strong clustering plus a mapper better than this flow's.
q = 1.48 is the measured transistor-count ratio of this flow to a fan-out-legalized
yosys+ABC netlist at W = 1; q = 1.77 is the ratio to the hand-optimized fabricated
chip.  Combinational-only scaling, since the 18-transistor flip-flop cost is fixed
by the library.

| q | alpha* (f_max) | alpha* (1 kHz) |
|--:|--:|--:|
| 1.00 | 3.7 | 5.0 |
| 1.48 | 4.8 | 7.1 |
| 1.77 | 5.8 | 9.2 |

alpha* is the smallest clustering parameter at which the envelope still selects
bit-serial at the anchor: the retrodiction holds for alpha > alpha* and fails below
it.  The binding corner is the fixed 1 kHz clock with q = 1.77.

## 3. Boundary ladders

### f_max operation, q = 1

| alpha | switch 1 | switch 2 | switch 3 | envelope |
|--:|--:|--:|--:|:--|
| inf | 41 | 92 | 198 | W=32 prefix -> W=16 prefix -> W=8 prefix -> W=1 ripple |
| 10 | 45 | 113 | 275 | W=32 prefix -> W=16 prefix -> W=8 prefix -> W=1 ripple |
| 5 | 50 | 145 | 446 | W=32 prefix -> W=16 prefix -> W=8 prefix -> W=1 ripple |
| 3 | 60 | 234 | 2437 | W=32 prefix -> W=16 prefix -> W=8 prefix -> W=1 ripple |
| 2 | 79 | 989 | -- | W=32 prefix -> W=16 prefix -> W=8 prefix |
| 1 | 1840 | -- | -- | W=32 prefix -> W=16 prefix |
| 0.5 | -- | -- | -- | W=32 prefix |

Switch columns are defects per 10^6 transistors at the successive envelope
boundaries, widest design first.  Under strong clustering the envelope loses
widths entirely -- the transistor-count advantage of serialization stops buying
yield -- which is why table 1 rather than this one is the statement of the test.
### fixed 1 kHz clock, q = 1

| alpha | switch 1 | switch 2 | switch 3 | envelope |
|--:|--:|--:|--:|:--|
| inf | 67 | 156 | 249 | W=32 ripple -> W=16 ripple -> W=8 ripple -> W=1 ripple |
| 10 | 80 | 223 | 383 | W=32 ripple -> W=16 ripple -> W=8 ripple -> W=1 ripple |
| 5 | 98 | 388 | 810 | W=32 ripple -> W=16 ripple -> W=8 ripple -> W=1 ripple |
| 3 | 140 | -- | -- | W=32 ripple -> W=16 ripple |
| 2 | 301 | -- | -- | W=32 ripple -> W=16 ripple |
| 1 | -- | -- | -- | W=32 ripple |
| 0.5 | -- | -- | -- | W=32 ripple |

Switch columns are defects per 10^6 transistors at the successive envelope
boundaries, widest design first.  Under strong clustering the envelope loses
widths entirely -- the transistor-count advantage of serialization stops buying
yield -- which is why table 1 rather than this one is the statement of the test.
