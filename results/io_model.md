External-interface cost model (audit A-1)

Table IO-1: external pin count and measured pad activity (checksum workload, gate level)

| W | adder | N_io pins | pad-bit toggles / instr | E_io/instr uJ (C_pad=10pF) | delay+2 pad crossings us | f_max' Hz |
|--:|:--|--:|--:|--:|--:|--:|
| 1 | ripple | 193 | 318.2 | 0.051 | 261.2 | 3828 |
| 2 | ripple | 195 | 179.6 | 0.029 | 303.4 | 3296 |
| 4 | ripple | 200 | 130.6 | 0.021 | 345.3 | 2896 |
| 8 | ripple | 211 | 103.2 | 0.017 | 426.0 | 2347 |
| 16 | ripple | 234 | 90.9 | 0.015 | 586.8 | 1704 |
| 32 | ripple | 282 | 73.2 | 0.012 | 894.7 | 1118 |
| 8 | prefix | 211 | 103.2 | 0.017 | 354.3 | 2822 |
| 16 | prefix | 234 | 90.9 | 0.015 | 405.7 | 2465 |
| 32 | prefix | 282 | 73.2 | 0.012 | 446.5 | 2240 |

The measured pad-bit toggles per instruction are width-comparable (serial designs toggle few wires many times, parallel designs many wires once), so pad ENERGY does not select a width; pad COUNT does, through area and yield (Table IO-2).

C_pad sensitivity: E1k(W=1) - E1k(W=32) = 31.15 uJ (static) + (+245.0 pad-toggles/instr) x C_pad x Vdd^2. Both terms favor W = 32: NO finite C_pad reverses the parallel energy advantage.

Table IO-2: pad-aware yield boundaries, T_eff = T + rho x N_io (f_max metric, gamma_w = 1)

| rho [T-equiv/pin] | envelope (d* in defects/10^6 T) |
|:--|:--|
| 0 | W=32 prefix -> W=16 prefix (41) -> W=8 prefix (92) -> W=1 ripple (198) |
| 300 | W=32 prefix -> W=16 prefix (12) -> W=8 prefix (30) -> W=4 ripple (106) -> W=1 ripple (121) |
| 1000 | W=32 prefix -> W=16 prefix (4) -> W=8 prefix (12) -> W=4 ripple (41) -> W=1 ripple (75) |

(rho taxes exactly the resource where serialization wins.  The envelope ORDER is unchanged, but large pad costs compress every boundary toward lower defect density -- at rho = 300 the top switch moves 41 -> 12 per 10^6 T and a narrow W = 4 window opens -- i.e. expensive pads make serialization pay off EARLIER, while never changing which widths appear on the envelope.  rho = 1000 T-equivalents/pin means the pad ring exceeds the W = 1 core itself by 18x, an extreme bound.)
