Standalone W-bit adders (pre-buffering) with wire-span analysis

| W | adder | T | depth | delay us (c_bit=0) | S_lin (pitches) | S_quad (pitches^2) |
|--:|:--|--:|--:|--:|--:|--:|
| 4 | ripple | 172 | 12 | 85.8 | 4 | 4 |
| 4 | prefix | 190 | 7 | 55.0 | 4 | 6 |
| 8 | ripple | 344 | 24 | 164.5 | 8 | 8 |
| 8 | prefix | 421 | 11 | 83.2 | 8 | 22 |
| 16 | ripple | 688 | 48 | 321.9 | 16 | 16 |
| 16 | prefix | 912 | 16 | 118.5 | 16 | 86 |
| 32 | ripple | 1376 | 96 | 636.8 | 32 | 32 |
| 32 | prefix | 1895 | 20 | 149.8 | 32 | 342 |

Crossover wire capacitance c_bit* where ripple becomes faster than Brent-Kung (delay0 + SLOPE*c_bit*S model):

| W | linear-C c_bit* | distributed-RC c_bit* |
|--:|:--|:--|
| 4 | none (BK wire path shorter than ripple's) | 25.667 pF/pitch |
| 8 | none (BK wire path shorter than ripple's) | 9.676 pF/pitch |
| 16 | none (BK wire path shorter than ripple's) | 4.843 pF/pitch |
| 32 | none (BK wire path shorter than ripple's) | 2.619 pF/pitch |
