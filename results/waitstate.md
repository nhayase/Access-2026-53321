CPI with a width-limited memory bus (3 wait states per bus transaction, ~ 8-bit external bus)

| W | adder | checksum | memcpy | softmul | sort | popcount | geomean | vs zero-wait | E/instr uJ @1kHz |
|--:|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| 1 | ripple | 51.44 | 51.22 | 58.62 | 57.74 | 49.98 | 53.68 | x1.07 | 40.85 |
| 2 | ripple | 28.22 | 29.27 | 31.78 | 31.97 | 27.41 | 29.67 | x1.14 | 33.86 |
| 4 | ripple | 16.95 | 18.29 | 18.45 | 19.09 | 16.22 | 17.77 | x1.26 | 21.13 |
| 8 | ripple | 11.32 | 12.80 | 11.78 | 12.64 | 10.62 | 11.81 | x1.45 | 15.23 |
| 16 | ripple | 8.51 | 10.06 | 8.45 | 9.42 | 7.83 | 8.82 | x1.70 | 13.24 |
| 32 | ripple | 7.10 | 8.69 | 6.78 | 7.81 | 6.43 | 7.32 | x1.98 | 13.66 |
| 8 | prefix | 11.32 | 12.80 | 11.78 | 12.64 | 10.62 | 11.81 | x1.45 | 15.43 |
| 16 | prefix | 8.51 | 10.06 | 8.45 | 9.42 | 7.83 | 8.82 | x1.70 | 13.67 |
| 32 | prefix | 7.10 | 8.69 | 6.78 | 7.81 | 6.43 | 7.32 | x1.98 | 14.46 |

Serial/parallel CPI ratio: 13.5x (zero-wait) -> 7.3x (3 waits): a slow memory compresses the parallel CPI advantage but does not reorder any conclusion (energy at 1 kHz remains T-dominated).
