## Effective wire factor lambda_eff(W, k) = C_eff / 2.5 pF (architecture- and tier-dependent)

| W | adder | N cells | flat (k=1) | 2-tier | 4-tier |
|--:|:--|--:|--:|--:|--:|
| 1 | ripple | 1696 | 1.000 | 0.719 | 0.520 |
| 2 | ripple | 2534 | 1.039 | 0.747 | 0.540 |
| 4 | ripple | 2664 | 1.044 | 0.750 | 0.542 |
| 8 | ripple | 2937 | 1.054 | 0.757 | 0.547 |
| 16 | ripple | 3510 | 1.072 | 0.770 | 0.556 |
| 32 | ripple | 4526 | 1.099 | 0.789 | 0.570 |
| 8 | prefix | 2978 | 1.056 | 0.758 | 0.548 |
| 16 | prefix | 3646 | 1.076 | 0.773 | 0.558 |
| 32 | prefix | 4831 | 1.106 | 0.794 | 0.573 |

(The flat W=1 value is 1.000 by calibration; lambda_eff grows with W through the Rent/Donath wirelength L(N) and falls with 1/sqrt(k).)

## Feasibility-frontier coefficients: delay = gt (D0 + D1 gw) [us]

Every phase boundary of PD-1 is gt (D0 + D1 gw) = 1/f_op.

| W | adder | n stages | D0 (k=1) | D1 (k=1) | D1 (k=2) | D1 (k=4) |
|--:|:--|--:|--:|--:|--:|--:|
| 1 | ripple | 35 | 146.1 | 95.0 | 67.2 | 47.5 |
| 2 | ripple | 38 | 159.4 | 128.9 | 91.2 | 64.5 |
| 4 | ripple | 45 | 188.4 | 143.1 | 101.2 | 71.6 |
| 8 | ripple | 56 | 234.5 | 181.0 | 128.0 | 90.5 |
| 16 | ripple | 79 | 330.6 | 254.0 | 179.6 | 127.0 |
| 32 | ripple | 126 | 526.1 | 384.4 | 271.8 | 192.2 |
| 8 | prefix | 45 | 188.8 | 153.9 | 108.8 | 76.9 |
| 16 | prefix | 51 | 214.2 | 185.0 | 130.8 | 92.5 |
| 32 | prefix | 57 | 239.2 | 207.9 | 147.0 | 103.9 |

## PD-1: optimal W at fixed f_op = 1000 Hz, flat (k=1)

x: wire penalty gamma_w, y: device delay penalty gamma_t (1 = measured MoS2 2025 values; region = widest feasible design, which is simultaneously throughput- and energy-optimal among the feasible set)

```
    rows: gamma_t (top = max), cols: gamma_w (left = min)
    .................................   10
    .................................   7.94328
    ss...............................   6.30957
    ddddddddsssss....................   5.01187
    HHHHHBBBBBndddsss................   3.98107
    PPPPPPPPPPHHBBBnddsss............   3.16228
    PPPPPPPPPPPPPPPHBBBddss..........   2.51189
    PPPPPPPPPPPPPPPPPPHHBndsss.......   1.99526
    pppppppPPPPPPPPPPPPPPHBBddss.....   1.58489
    ppppppppppppppPPPPPPPPPHBBndss...   1.25893
    ppppppppppppppppppPPPPPPPPHBndss.   1
    pppppppppppppppppppppPPPPPPPHBdss   0.794328
    ppppppppppppppppppppppppPPPPPHBBd   0.630957
    ppppppppppppppppppppppppppPPPPPHB   0.501187
    ppppppppppppppppppppppppppppPPPPP   0.398107
    ppppppppppppppppppppppppppppppPPP   0.316228
    ppppppppppppppppppppppppppppppppP   0.251189
    ppppppppppppppppppppppppppppppppp   0.199526
    ppppppppppppppppppppppppppppppppp   0.158489
    ppppppppppppppppppppppppppppppppp   0.125893
    ppppppppppppppppppppppppppppppppp   0.1
    |       |       |       |       |
    0.1     0.32    1       3.2     10      
```
legend: s=1  d=2  n=4  b/B=8  h/H=16  p/P=32 (lowercase ripple, UPPERCASE Brent-Kung prefix), .=infeasible

Boundaries along gamma_t = 1 (gw* where each design becomes infeasible): W=32 ripple: gw*=1.23, W=16 ripple: gw*=2.64, W=32 prefix: gw*=3.66, W=8 ripple: gw*=4.23, W=16 prefix: gw*=4.25, W=8 prefix: gw*=5.27, W=4 ripple: gw*=5.67, W=2 ripple: gw*=6.52, W=1 ripple: gw*=8.99

## PD-1: optimal W at fixed f_op = 1000 Hz, 2-tier M3D

x: wire penalty gamma_w, y: device delay penalty gamma_t (1 = measured MoS2 2025 values; region = widest feasible design, which is simultaneously throughput- and energy-optimal among the feasible set)

```
    rows: gamma_t (top = max), cols: gamma_w (left = min)
    .................................   10
    .................................   7.94328
    sssss............................   6.30957
    nddddddddddssss..................   5.01187
    HHHHHHHHBBBBBddddsss.............   3.98107
    PPPPPPPPPPPPHHHBBBddsss..........   3.16228
    PPPPPPPPPPPPPPPPPHHBBndsss.......   2.51189
    PPPPPPPPPPPPPPPPPPPPPHBBddss.....   1.99526
    ppppppppppPPPPPPPPPPPPPHHBndss...   1.58489
    ppppppppppppppppPPPPPPPPPPHBndss.   1.25893
    ppppppppppppppppppppPPPPPPPPHBnds   1
    pppppppppppppppppppppppPPPPPPPHBn   0.794328
    ppppppppppppppppppppppppppPPPPPPH   0.630957
    ppppppppppppppppppppppppppppPPPPP   0.501187
    ppppppppppppppppppppppppppppppPPP   0.398107
    ppppppppppppppppppppppppppppppppP   0.316228
    ppppppppppppppppppppppppppppppppp   0.251189
    ppppppppppppppppppppppppppppppppp   0.199526
    ppppppppppppppppppppppppppppppppp   0.158489
    ppppppppppppppppppppppppppppppppp   0.125893
    ppppppppppppppppppppppppppppppppp   0.1
    |       |       |       |       |
    0.1     0.32    1       3.2     10      
```
legend: s=1  d=2  n=4  b/B=8  h/H=16  p/P=32 (lowercase ripple, UPPERCASE Brent-Kung prefix), .=infeasible

Boundaries along gamma_t = 1 (gw* where each design becomes infeasible): W=32 ripple: gw*=1.74, W=16 ripple: gw*=3.73, W=32 prefix: gw*=5.18, W=8 ripple: gw*=5.98, W=16 prefix: gw*=6.01, W=8 prefix: gw*=7.46, W=4 ripple: gw*=8.02, W=2 ripple: gw*=9.22, W=1 ripple: gw*=12.71

## PD-1: optimal W at fixed f_op = 1000 Hz, 4-tier M3D

x: wire penalty gamma_w, y: device delay penalty gamma_t (1 = measured MoS2 2025 values; region = widest feasible design, which is simultaneously throughput- and energy-optimal among the feasible set)

```
    rows: gamma_t (top = max), cols: gamma_w (left = min)
    .................................   10
    .................................   7.94328
    sssssss..........................   6.30957
    BBBndddddddddssss................   5.01187
    PHHHHHHHHHBBBBBndddsss...........   3.98107
    PPPPPPPPPPPPPPHHHBBBnddss........   3.16228
    PPPPPPPPPPPPPPPPPPPHHBBnddss.....   2.51189
    PPPPPPPPPPPPPPPPPPPPPPPHBBndss...   1.99526
    ppppppppppppPPPPPPPPPPPPPPHBBdsss   1.58489
    pppppppppppppppppppPPPPPPPPPHBBds   1.25893
    pppppppppppppppppppppppPPPPPPPHBB   1
    ppppppppppppppppppppppppppPPPPPPH   0.794328
    ppppppppppppppppppppppppppppPPPPP   0.630957
    pppppppppppppppppppppppppppppppPP   0.501187
    ppppppppppppppppppppppppppppppppp   0.398107
    ppppppppppppppppppppppppppppppppp   0.316228
    ppppppppppppppppppppppppppppppppp   0.251189
    ppppppppppppppppppppppppppppppppp   0.199526
    ppppppppppppppppppppppppppppppppp   0.158489
    ppppppppppppppppppppppppppppppppp   0.125893
    ppppppppppppppppppppppppppppppppp   0.1
    |       |       |       |       |
    0.1     0.32    1       3.2     10      
```
legend: s=1  d=2  n=4  b/B=8  h/H=16  p/P=32 (lowercase ripple, UPPERCASE Brent-Kung prefix), .=infeasible

Boundaries along gamma_t = 1 (gw* where each design becomes infeasible): W=32 ripple: gw*=2.47, W=16 ripple: gw*=5.27, W=32 prefix: gw*=7.32, W=8 ripple: gw*=8.46, W=16 prefix: gw*=8.50, W=8 prefix: gw*=10.54, W=4 ripple: gw*=11.34, W=2 ripple: gw*=13.04, W=1 ripple: gw*=17.97

## PD-2: optimal W over wire penalty x defect density (throughput per die at f_max, flat)

x: gamma_w, y: defect density d [defects/transistor]

```
    rows: d (top = max), cols: gamma_w (left = min)
    sssssssssssssssssssssssssssssssss   0.001
    sssssssssssssssssssssssssssssssss   0.000707946
    sssssssssssssssssssssssssssssssss   0.000501187
    sssssssssssssssssssssssssssssssss   0.000354813
    sssssssssssssssssssssssssssssssss   0.000251189
    BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB   0.000177828
    BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB   0.000125893
    HHHHHHHHHHHHHHHHHBBBBBBBBBBBBBBBB   8.91251e-05
    HHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHH   6.30957e-05
    HHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHH   4.46684e-05
    PPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPP   3.16228e-05
    PPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPP   2.23872e-05
    PPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPP   1.58489e-05
    PPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPP   1.12202e-05
    PPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPP   7.94328e-06
    PPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPP   5.62341e-06
    PPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPP   3.98107e-06
    PPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPP   2.81838e-06
    PPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPP   1.99526e-06
    PPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPP   1.41254e-06
    PPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPP   1e-06
    |       |       |       |       |
    0.1     0.32    1       3.2     10      
```
legend: s=1  d=2  n=4  b/B=8  h/H=16  p/P=32 (lowercase ripple, UPPERCASE Brent-Kung prefix), .=infeasible

gamma_w = 0.3: W=32 prefix -> W=16 prefix (d*=39/10^6 T) -> W=8 prefix (d*=94/10^6 T) -> W=1 ripple (d*=202/10^6 T)

gamma_w = 1: W=32 prefix -> W=16 prefix (d*=38/10^6 T) -> W=8 prefix (d*=90/10^6 T) -> W=1 ripple (d*=195/10^6 T)

gamma_w = 3: W=32 prefix -> W=16 prefix (d*=38/10^6 T) -> W=8 prefix (d*=85/10^6 T) -> W=1 ripple (d*=187/10^6 T)

gamma_w = 10: W=32 prefix -> W=16 prefix (d*=38/10^6 T) -> W=8 prefix (d*=82/10^6 T) -> W=1 ripple (d*=181/10^6 T)

## PD-3: energy-optimal W at f_max over wire penalty x static power, flat

x: gamma_w, y: p_s [nW/T] (72.67 = measured E/D NMOS, <0.1 = CFET leakage)

```
    rows: p_s (top = max), cols: gamma_w (left = min)
    HHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHH   100
    HHHHHHHHHHHHHHHHHHHHHPPPPPPPPPPPP   63.0957
    HHHHHHHHHHHHHPPPPPPPPPPPPPPPPPPPP   39.8107
    HHHHHHHPPPPPPPPPPPPPPPPPPPPPPPPPP   25.1189
    HHPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPP   15.8489
    PPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPP   10
    PPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPP   6.30957
    PPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPP   3.98107
    PPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPP   2.51189
    PPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPP   1.58489
    PPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPP   1
    PPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPP   0.630957
    PPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPP   0.398107
    PPPPPPPPPPPPPPPPPPPPPPPPPPPPPpppp   0.251189
    PPPPPPPPPPPPPPPPPPPPppppppppppppp   0.158489
    PPPPPPPPPPPPPPppppppppppppppppppp   0.1
    PPPPPPPPPPppppppppppppppppppppppp   0.0630957
    PPPPPpppppppppppppppppppppppppppp   0.0398107
    Ppppppppppppppppppppppppppppppppp   0.0251189
    ppppppppppppppppppppppppppppppppp   0.0158489
    ppppppppppppppppppppppppppppppppp   0.01
    |       |       |       |       |
    0.1     0.32    1       3.2     10      
```
legend: s=1  d=2  n=4  b/B=8  h/H=16  p/P=32 (lowercase ripple, UPPERCASE Brent-Kung prefix), .=infeasible

## PD-3: energy-optimal W at f_max over wire penalty x static power, 4-tier M3D

x: gamma_w, y: p_s [nW/T] (72.67 = measured E/D NMOS, <0.1 = CFET leakage)

```
    rows: p_s (top = max), cols: gamma_w (left = min)
    HHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHH   100
    HHHHHHHHHHHHHHHHHHHHHHHHHHPPPPPPP   63.0957
    HHHHHHHHHHHHHHHHHHPPPPPPPPPPPPPPP   39.8107
    HHHHHHHHHHHHPPPPPPPPPPPPPPPPPPPPP   25.1189
    HHHHHHHPPPPPPPPPPPPPPPPPPPPPPPPPP   15.8489
    HPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPP   10
    PPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPP   6.30957
    PPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPP   3.98107
    PPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPP   2.51189
    PPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPP   1.58489
    PPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPP   1
    PPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPP   0.630957
    PPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPP   0.398107
    PPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPP   0.251189
    PPPPPPPPPPPPPPPPPPPPPPPPppppppppp   0.158489
    PPPPPPPPPPPPPPPPPPPpppppppppppppp   0.1
    PPPPPPPPPPPPPPppppppppppppppppppp   0.0630957
    PPPPPPPPPPppppppppppppppppppppppp   0.0398107
    PPPPPPppppppppppppppppppppppppppp   0.0251189
    Ppppppppppppppppppppppppppppppppp   0.0158489
    ppppppppppppppppppppppppppppppppp   0.01
    |       |       |       |       |
    0.1     0.32    1       3.2     10      
```
legend: s=1  d=2  n=4  b/B=8  h/H=16  p/P=32 (lowercase ripple, UPPERCASE Brent-Kung prefix), .=infeasible
