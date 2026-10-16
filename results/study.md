Table 1: synthesis results (RV32-WUJI PDK flow)

| W | adder | cells | DFF | T (NMOS) | depth (pre-buf) | depth<=17 | fan-out viol. | delay us |
|--:|:--|--:|--:|--:|--:|:--:|--:|--:|
| 1 | ripple | 1696 | 145 | 10474 | 34 (29) | FAIL | 0 | 241.1 |
| 2 | ripple | 2534 | 139 | 15705 | 37 (30) | FAIL | 0 | 283.3 |
| 4 | ripple | 2664 | 138 | 16359 | 44 (35) | FAIL | 0 | 325.2 |
| 8 | ripple | 2937 | 137 | 17748 | 55 (46) | FAIL | 0 | 405.9 |
| 16 | ripple | 3510 | 136 | 20649 | 78 (69) | FAIL | 0 | 566.7 |
| 32 | ripple | 4526 | 135 | 25679 | 125 (114) | FAIL | 0 | 874.6 |
| 8 | prefix | 2978 | 137 | 17979 | 44 (35) | FAIL | 0 | 334.2 |
| 16 | prefix | 3646 | 136 | 21327 | 50 (39) | FAIL | 0 | 385.6 |
| 32 | prefix | 4831 | 135 | 27195 | 56 (41) | FAIL | 0 | 426.4 |

Table 2: CPI per workload (cycle-accurate, zero-wait memory; results asserted identical across design points)

| W | adder | checksum | memcpy | softmul | sort | popcount | geomean |
|--:|:--|--:|--:|--:|--:|--:|--:|
| 1 | ripple | 47.92 | 46.48 | 55.52 | 53.84 | 46.96 | 50.0 |
| 2 | ripple | 24.7 | 24.52 | 28.68 | 28.07 | 24.39 | 26.0 |
| 4 | ripple | 13.43 | 13.55 | 15.35 | 15.18 | 13.2 | 14.11 |
| 8 | ripple | 7.8 | 8.06 | 8.68 | 8.74 | 7.6 | 8.16 |
| 16 | ripple | 4.98 | 5.31 | 5.35 | 5.52 | 4.8 | 5.19 |
| 32 | ripple | 3.58 | 3.94 | 3.68 | 3.91 | 3.41 | 3.7 |
| 8 | prefix | 7.8 | 8.06 | 8.68 | 8.74 | 7.6 | 8.16 |
| 16 | prefix | 4.98 | 5.31 | 5.35 | 5.52 | 4.8 | 5.19 |
| 32 | prefix | 3.58 | 3.94 | 3.68 | 3.91 | 3.41 | 3.7 |

Table 3: performance and energy, Scenario A (measured PDK, static-dominated; geomean CPI)

| W | adder | f_max Hz | instr/s @f_max | E/instr uJ @f_max | instr/s @1kHz | E/instr uJ @1kHz | P mW |
|--:|:--|--:|--:|--:|--:|--:|--:|
| 1 | ripple | 4147.7 | 82.9 | 9.175 | 20.0 | 38.05 | 0.761 |
| 2 | ripple | 3530.1 | 135.7 | 8.405 | 38.5 | 29.67 | 1.141 |
| 4 | ripple | 3075.0 | 217.9 | 5.457 | 70.9 | 16.78 | 1.189 |
| 8 | ripple | 2463.9 | 301.8 | 4.274 | 122.5 | 10.53 | 1.29 |
| 16 | ripple | 1764.5 | 340.1 | 4.413 | 192.8 | 7.79 | 1.501 |
| 32 | ripple | 1143.4 | 309.2 | 6.035 | 270.4 | 6.9 | 1.866 |
| 8 | prefix | 2992.2 | 366.5 | 3.566 | 122.5 | 10.67 | 1.307 |
| 16 | prefix | 2593.6 | 499.9 | 3.1 | 192.8 | 8.04 | 1.55 |
| 32 | prefix | 2345.1 | 634.2 | 3.116 | 270.4 | 7.31 | 1.976 |

Table 4: Scenario B baseline (2D CFET, M3D k=4, gamma_w=1; architecture-dependent wire model, MEASURED per-design alpha)

| W | adder | T (CMOS) | pins | C_eff pF/pin | alpha (meas.) | E_dyn/instr nJ |
|--:|:--|--:|--:|--:|--:|--:|
| 1 | ripple | 13214 | 3316 | 1.3 | 0.0453 | 156.24 |
| 2 | ripple | 19956 | 5194 | 1.35 | 0.0571 | 166.49 |
| 4 | ripple | 20762 | 5438 | 1.36 | 0.0763 | 126.99 |
| 8 | ripple | 22474 | 5950 | 1.37 | 0.0978 | 103.97 |
| 16 | ripple | 26046 | 7018 | 1.39 | 0.1196 | 96.88 |
| 32 | ripple | 32210 | 8873 | 1.42 | 0.1028 | 76.84 |
| 8 | prefix | 22772 | 6042 | 1.37 | 0.0982 | 106.14 |
| 16 | prefix | 26894 | 7292 | 1.4 | 0.1193 | 100.77 |
| 32 | prefix | 34098 | 9486 | 1.43 | 0.0989 | 79.51 |

Table 5: gate-level workload execution (checksum): cycle count asserted equal to RTL, checksum asserted equal to the golden ISS, per-design measured switching activity and pad-bit toggles

| W | adder | alpha measured | pad-bit toggles/instr |
|--:|:--|--:|--:|
| 1 | ripple | 0.0453 | 318.2 |
| 2 | ripple | 0.0571 | 179.6 |
| 4 | ripple | 0.0763 | 130.6 |
| 8 | ripple | 0.0978 | 103.2 |
| 16 | ripple | 0.1196 | 90.9 |
| 32 | ripple | 0.1028 | 73.2 |
| 8 | prefix | 0.0982 | 103.2 |
| 16 | prefix | 0.1193 | 90.9 |
| 32 | prefix | 0.0989 | 73.2 |
