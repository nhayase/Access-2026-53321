Boundary analysis: where does the optimal design point switch?

## (a) Defect density (yield axis)

Metric: expected throughput per fabricated die, E[thr] = exp(-d T) x thr.  d* boundaries are exact (d* = ln(thr_i/thr_j)/(T_i - T_j)); also expressed as the yield the W = 1 core would have at that defect density.

### fixed 1 kHz operation

| optimal design | from d [1/T] | i.e. defects/10^6 T | yield of W=1 core there |
|:--|:--|--:|--:|
| W=32 ripple | d -> 0 | -- | -- |
| W=16 ripple | 6.728e-05 | 67 | 49 % |
| W=8 ripple | 1.560e-04 | 156 | 20 % |
| W=1 ripple | 2.492e-04 | 249 | 7 % |

### f_max operation

| optimal design | from d [1/T] | i.e. defects/10^6 T | yield of W=1 core there |
|:--|:--|--:|--:|
| W=32 prefix | d -> 0 | -- | -- |
| W=16 prefix | 4.050e-05 | 41 | 65 % |
| W=8 prefix | 9.246e-05 | 92 | 38 % |
| W=1 ripple | 1.980e-04 | 198 | 13 % |

## (b) Frequency target (feasibility axis)

Throughput-optimal design vs. required clock f_req (design feasible iff critical-path delay < 1/f_req; among feasible designs the lowest-CPI one wins since thr = f_req / CPI):

| f_req range | optimal design | limiting delay |
|:--|:--|:--|
| 0 - 1143 Hz | W=32 ripple | 874.6 us |
| 0 - 2345 Hz | W=32 prefix | 426.4 us |
| 2345 - 2593 Hz | W=16 prefix | 385.6 us |
| 2593 - 2992 Hz | W=8 prefix | 334.2 us |
| 2992 - 3075 Hz | W=4 ripple | 325.2 us |
| 3075 - 3530 Hz | W=2 ripple | 283.3 us |
| 3530 - 4148 Hz | W=1 ripple | 241.1 us |
| > 4148 Hz | infeasible in this library | -- |

## (c) M3D tiers k and wire factor gamma_w (Scenario B)

Optimal W by dynamic energy/instruction and by throughput at the wire-scaled f_max (architecture-dependent C_eff = C_G + gamma_w c_w L(N)/sqrt(k)):

| k | gamma_w | E_dyn-optimal | thr-optimal | C_eff(W=1) pF | C_eff(W=32 prefix) pF |
|--:|--:|:--|:--|--:|--:|
| 1 | 1.0 | W=32 ripple (144.3 nJ) | W=32 prefix (605 i/s) | 2.50 | 2.76 |
| 1 | 0.3 | W=32 ripple (47.0 nJ) | W=32 prefix (896 i/s) | 0.82 | 0.90 |
| 1 | 0.1 | W=32 ripple (19.2 nJ) | W=32 prefix (1039 i/s) | 0.34 | 0.37 |
| 2 | 1.0 | W=32 ripple (103.6 nJ) | W=32 prefix (700 i/s) | 1.80 | 1.98 |
| 2 | 0.3 | W=32 ripple (34.8 nJ) | W=32 prefix (954 i/s) | 0.61 | 0.67 |
| 2 | 0.1 | W=32 ripple (15.1 nJ) | W=32 prefix (1064 i/s) | 0.27 | 0.29 |
| 4 | 1.0 | W=32 ripple (74.8 nJ) | W=32 prefix (788 i/s) | 1.30 | 1.43 |
| 4 | 0.3 | W=32 ripple (26.1 nJ) | W=32 prefix (1000 i/s) | 0.46 | 0.50 |
| 4 | 0.1 | W=32 ripple (12.2 nJ) | W=32 prefix (1083 i/s) | 0.22 | 0.23 |
| 8 | 1.0 | W=32 ripple (54.4 nJ) | W=32 prefix (864 i/s) | 0.95 | 1.04 |
| 8 | 0.3 | W=32 ripple (20.0 nJ) | W=32 prefix (1034 i/s) | 0.35 | 0.38 |
| 8 | 0.1 | W=32 ripple (10.2 nJ) | W=32 prefix (1096 i/s) | 0.18 | 0.19 |

## (d) Static power per transistor p_s (NMOS -> CFET transition)

Energy/instruction at 1 kHz, E = (p_s T + P_dyn) CPI / f with the baseline wire model (k=1, gamma_w=1).  Optimal W vs. p_s:

| p_s [nW/T] | E-optimal design | E/instr |
|--:|:--|:--|
| 72.67 | W=32 ripple | 7.05 uJ |
| 30 | W=32 ripple | 2.99 uJ |
| 10 | W=32 ripple | 1.09 uJ |
| 3 | W=32 ripple | 0.43 uJ |
| 1 | W=32 ripple | 0.24 uJ |
| 0.3 | W=32 ripple | 0.17 uJ |
| 0.1 | W=32 ripple | 0.15 uJ |
| 0.01 | W=32 ripple | 0.15 uJ |

No switch on this axis at the fixed 1 kHz clock: the energy-optimal width is the same for every p_s (both p_s T CPI and N_pins C_eff CPI are minimized by the same design).  This holds under fixed-clock or race-to-sleep operation only; under iso-throughput operation without power gating the static term scales with T alone and favors serialization (article, Section IV-C).  The energy-optimal width at f_max is mapped in the article's Fig. 5.
