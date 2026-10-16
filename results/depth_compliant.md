Depth-compliant (<= 17 stages) sub-cycle-pipelined physical netlists; physical clock = 171.02 us (5847 Hz), one architectural cycle = S periods

Table A: construction (m2d/pdk2d/pipeline.py). 'cuts' are the logic levels after which the pipeline registers sit (chosen to minimize their number under the <= 17-level band constraint), 'cut regs' the DFFHQ inserted there, 'hold MUX' the MUX2 in front of the architectural flip-flops ('hold-less' architectural flip-flops need none), 'ring' the ring-counter cells, 'buffers' the INV added for fan-out. The analytic columns are the v6.3 estimate (S = ceil(depth/17), one register per net and crossed cut, no hold logic).

| W | adder | depth | S analytic | regs analytic | T analytic | S | max endpoint level | cuts after level | cut regs | hold MUX | hold-less FFs | ring cells | buffers | T_c | T_c / T |
|--:|:--|--:|--:|--:|--:|--:|--:|:--|--:|--:|--:|--:|--:|--:|--:|
| 1 | ripple | 34 | 2 | 290 | 15694 | 2 | 34 | 17 | 198 | 134 | 11 | 5 | 104 | 15500 | 1.48 |
| 2 | ripple | 37 | 3 | 727 | 28791 | 3 | 38 | 17, 34 | 549 | 139 | 0 | 7 | 109 | 27127 | 1.73 |
| 4 | ripple | 44 | 3 | 939 | 33261 | 3 | 45 | 17, 34 | 767 | 137 | 1 | 7 | 117 | 31703 | 1.94 |
| 8 | ripple | 55 | 4 | 1346 | 41976 | 4 | 56 | 17, 34, 51 | 1068 | 137 | 0 | 9 | 133 | 38565 | 2.17 |
| 16 | ripple | 78 | 5 | 2320 | 62409 | 5 | 79 | 17, 34, 51, 68 | 1953 | 135 | 1 | 11 | 156 | 57447 | 2.78 |
| 32 | ripple | 125 | 8 | 4756 | 111287 | 8 | 126 | 17, 34, 51, 68, 85, 102, 119 | 3953 | 135 | 0 | 20 | 104 | 98448 | 3.83 |
| 8 | prefix | 44 | 3 | 993 | 35853 | 3 | 45 | 17, 34 | 822 | 137 | 0 | 7 | 131 | 34341 | 1.91 |
| 16 | prefix | 50 | 3 | 1221 | 43305 | 3 | 51 | 17, 34 | 1050 | 136 | 0 | 7 | 154 | 41830 | 1.96 |
| 32 | prefix | 56 | 4 | 1866 | 60783 | 4 | 57 | 16, 33, 50 | 1514 | 135 | 0 | 9 | 102 | 55960 | 2.06 |

Table B: design-rule checks and verification of the physical netlists. 'depth' is the logic depth reported by the same analyzer as Table 1 of study.md; 'delay' the critical path per physical period; 'seq. equiv.' the number of random cases of the S-period sequential equivalence check against the mapped netlist (garbage-before-arrival environment); 'S-1 fails' whether the same netlist with a ring of S-1 phases fails that check; 'gate-level' the architectural cycles of the checksum workload executed on the physical netlist at sub-cycle granularity from a random initial state through reset, asserted equal to the RTL cycle count, with the result asserted equal to the golden ISS.

| W | adder | cells | DFF | depth | depth<=17 | fan-out viol. | NM | delay us | seq. equiv. | S-1 fails | gate-level arch cycles (= RTL) | physical periods | alpha / period | pad-bit toggles/instr |
|--:|:--|--:|--:|--:|:--:|--:|:--:|--:|--:|:--:|--:|--:|--:|--:|
| 1 | ripple | 2137 | 345 | 17 | PASS | 0 | PASS | 136.08 | 4096 | yes | 9393 (9393) | 18787 | 0.0703 | 320.5 |
| 2 | ripple | 3338 | 691 | 17 | PASS | 0 | PASS | 145.08 | 4096 | yes | 4841 (4841) | 14525 | 0.0394 | 181.9 |
| 4 | ripple | 3692 | 908 | 17 | PASS | 0 | PASS | 145.08 | 4096 | yes | 2633 (2633) | 7901 | 0.0441 | 132.8 |
| 8 | ripple | 4284 | 1209 | 17 | PASS | 0 | PASS | 148.08 | 4096 | yes | 1529 (1529) | 6119 | 0.0368 | 105.3 |
| 16 | ripple | 5765 | 2094 | 17 | PASS | 0 | PASS | 146.58 | 4096 | yes | 977 (977) | 4889 | 0.0319 | 93.1 |
| 32 | ripple | 8738 | 4096 | 17 | PASS | 0 | PASS | 146.58 | 4096 | yes | 701 (701) | 5615 | 0.0168 | 73.3 |
| 8 | prefix | 4075 | 962 | 17 | PASS | 0 | PASS | 149.58 | 4096 | yes | 1529 (1529) | 4589 | 0.0494 | 105.2 |
| 16 | prefix | 4993 | 1189 | 17 | PASS | 0 | PASS | 149.58 | 4096 | yes | 977 (977) | 2933 | 0.0537 | 93.2 |
| 32 | prefix | 6591 | 1653 | 17 | PASS | 0 | PASS | 145.08 | 4096 | yes | 701 (701) | 2807 | 0.0333 | 73.3 |

Table C: performance and energy under strict 17-stage compliance (physical clock 171.02 us; CPI_c = geomean CPI x S; static-dominated power of the physical netlist, 72.67 nW/T). The 1 kHz columns keep the paper's external clock as the physical clock.

| W | adder | S | T_c | P mW | CPI_c | instr/s @f_c | E/instr uJ @f_c | instr/s @1 kHz | E/instr uJ @1 kHz |
|--:|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| 1 | ripple | 2 | 15500 | 1.126 | 100.0 | 58.5 | 19.26 | 10.0 | 112.64 |
| 2 | ripple | 3 | 27127 | 1.971 | 78.0 | 75.0 | 26.3 | 12.8 | 153.76 |
| 4 | ripple | 3 | 31703 | 2.304 | 42.33 | 138.1 | 16.68 | 23.6 | 97.52 |
| 8 | ripple | 4 | 38565 | 2.802 | 32.64 | 179.1 | 15.64 | 30.6 | 91.47 |
| 16 | ripple | 5 | 57447 | 4.175 | 25.95 | 225.3 | 18.53 | 38.5 | 108.33 |
| 32 | ripple | 8 | 98448 | 7.154 | 29.6 | 197.5 | 36.22 | 33.8 | 211.76 |
| 8 | prefix | 3 | 34341 | 2.496 | 24.48 | 238.9 | 10.45 | 40.8 | 61.09 |
| 16 | prefix | 3 | 41830 | 3.04 | 15.57 | 375.5 | 8.09 | 64.2 | 47.33 |
| 32 | prefix | 4 | 55960 | 4.067 | 14.8 | 395.1 | 10.29 | 67.6 | 60.19 |

All 9 physical netlists pass every design rule of the paper (depth <= 17, fan-out <= 4, noise margin) and execute the workload with the RTL cycle count: yes.
Under strict 17-stage compliance the transistor minimum is W=1 ripple (15500 T), the throughput optimum is W=32 prefix (395 instr/s) and the energy optimum is W=16 prefix (8.09 uJ/instr); W=32 prefix delivers 6.8x the throughput of W=1 ripple for 3.6x the transistors and 1.9x less energy per instruction.
The main study (study.md, unpipelined netlists at f_max) has its throughput optimum at W=32 prefix and its energy optimum at W=16 prefix: the serial-vs-parallel ordering is unchanged under strict compliance.
The v6.3 analytic estimate is superseded by these implemented netlists; it is kept in Table A only to show the direction of its errors (it omitted the hold logic and counted registers on flip-flop outputs and input pads, which need none).
