# Table: register file and integrated system
| W | adder | T_RF | depth_RF | T_core | T_sys | T_sys/T_sys(W=1) | depth_sys | delay_sys (us) | f_max,sys (Hz) | E/instr 1 kHz (uJ) | S_sys | T_sys,c |
| 1 | ripple | 62,420 | 20 | 10474 | 72,869 | 1.00 | 38 | 290.3 | 3,445 | 264.77 | 3 | 104,581 |
| 2 | ripple | 59,148 | 19 | 15705 | 74,861 | 1.03 | 38 | 290.3 | 3,445 | 141.44 | 3 | 114,645 |
| 4 | ripple | 57,562 | 18 | 16359 | 73,939 | 1.01 | 45 | 332.3 | 3,009 | 75.82 | 3 | 114,079 |
| 8 | ripple | 57,364 | 17 | 17748 | 75,144 | 1.03 | 56 | 405.9 | 2,464 | 44.56 | 4 | 128,085 |
| 16 | ripple | 56,770 | 16 | 20649 | 77,468 | 1.06 | 78 | 566.7 | 1,765 | 29.22 | 5 | 155,112 |
| 32 | ripple | 56,290 | 16 | 25679 | 82,020 | 1.13 | 125 | 870.1 | 1,149 | 22.05 | 8 | 212,955 |
| 8 | prefix | 57,364 | 17 | 17979 | 75,379 | 1.03 | 45 | 336.8 | 2,969 | 44.70 | 3 | 116,402 |
| 16 | prefix | 56,770 | 16 | 21327 | 78,146 | 1.07 | 50 | 382.6 | 2,614 | 29.47 | 3 | 123,853 |
| 32 | prefix | 56,290 | 16 | 27195 | 83,540 | 1.15 | 56 | 426.4 | 2,345 | 22.46 | 4 | 139,817 |

# Ladders with the register file on the die
# Ladders with the register file on the die
delay budget, 1 kHz, per die: W=32 ripple (0) -> W=16 ripple (74) -> W=8 ripple (195) -> W=4 ripple (454) -> W=1 ripple (1182); margin x0.68
delay budget, 1 kHz, per area: W=32 ripple (0) -> W=16 ripple (62) -> W=8 ripple (182) -> W=4 ripple (441) -> W=1 ripple (1169); margin x0.68
delay budget, f_max/f_c, per die: W=32 prefix (0) -> W=16 prefix (43) -> W=8 prefix (117) -> W=4 ripple (371) -> W=1 ripple (1056); margin x0.76
delay budget, f_max/f_c, per area: W=32 prefix (0) -> W=16 prefix (30) -> W=8 prefix (104) -> W=4 ripple (358) -> W=1 ripple (1042); margin x0.77
cascade, 1 kHz, per die: W=32 prefix (0) -> W=16 prefix (3) -> W=8 prefix (61) -> W=1 ripple (153); margin x5.22
cascade, 1 kHz, per area: W=16 prefix (0) -> W=8 prefix (52) -> W=1 ripple (144); margin x5.55
cascade, f_max/f_c, per die: W=32 prefix (0) -> W=16 prefix (3) -> W=8 prefix (61) -> W=1 ripple (153); margin x5.22
cascade, f_max/f_c, per area: W=16 prefix (0) -> W=8 prefix (52) -> W=1 ripple (144); margin x5.55

# energy ratios with RF, fixed clock / iso-throughput
W=32 ripple fixed-clock ratio 12.01 T ratio 1.126
W=32 prefix fixed-clock ratio 11.79 T ratio 1.146
W=16 prefix fixed-clock ratio 8.98 T ratio 1.072
cascade W=32 prefix fixed-clock ratio 7.58 thr ratio 10.14 T ratio 1.34
cascade W=16 prefix fixed-clock ratio 8.13 thr ratio 9.63 T ratio 1.18

# die yield of the integrated W=1 system
at 800 ppm: 4.705264056856955e-26 ; d for 50% die yield: 9.5 ppm; for 10%: 31.6 ppm
core-only W=1 at 800 ppm: 0.00022882490161838255
