Closed-form CPI model vs. cycle-accurate measurement.
CPI_pred = sum over classes of the V2 cycle formulas weighted by the measured dynamic mix (+ SRX shamt stalls at W = 1).

| W | adder | checksum pred/meas | memcpy pred/meas | softmul pred/meas | sort pred/meas | popcount pred/meas |
|--:|:--|--:|--:|--:|--:|--:|
| 1 | ripple | 47.92/47.92 | 46.48/46.48 | 55.52/55.52 | 53.84/53.84 | 46.96/46.96 |
| 2 | ripple | 24.70/24.70 | 24.52/24.52 | 28.68/28.68 | 28.07/28.07 | 24.39/24.39 |
| 4 | ripple | 13.43/13.43 | 13.55/13.55 | 15.35/15.35 | 15.18/15.18 | 13.20/13.20 |
| 8 | ripple | 7.80/7.80 | 8.06/8.06 | 8.68/8.68 | 8.74/8.74 | 7.60/7.60 |
| 16 | ripple | 4.98/4.98 | 5.31/5.31 | 5.35/5.35 | 5.52/5.52 | 4.80/4.80 |
| 32 | ripple | 3.58/3.58 | 3.94/3.94 | 3.68/3.68 | 3.91/3.91 | 3.41/3.41 |
| 8 | prefix | 7.80/7.80 | 8.06/8.06 | 8.68/8.68 | 8.74/8.74 | 7.60/7.60 |
| 16 | prefix | 4.98/4.98 | 5.31/5.31 | 5.35/5.35 | 5.52/5.52 | 4.80/4.80 |
| 32 | prefix | 3.58/3.58 | 3.94/3.94 | 3.68/3.68 | 3.91/3.91 | 3.41/3.41 |

Maximum |prediction - measurement| over all 9 x 5 entries: 0.005 cycles/instruction.  The CPI of ANY instruction mix on any design point therefore follows from the mix alone; the five kernels validate the model rather than define the result.
