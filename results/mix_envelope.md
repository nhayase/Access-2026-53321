Exact envelope of CPI(W=1) / CPI(W=32) over ALL instruction mixes

CPI is linear in the class-frequency vector, so the ratio is a ratio of
linear forms on the simplex and its extrema are attained at vertices, i.e.
at single-class programs.  This bound is exact and complete.

| class | W=1 | W=32 | ratio |
|:--|--:|--:|--:|
| alu | 34 | 3 | 11.333 |
| shift | 66 | 4 | 16.500 |
| compare | 66 | 4 | 16.500 |
| load | 67 | 5 | 13.400 |
| store | 35 | 4 | 8.750 |
| branch | 66 | 4 | 16.500 |
| jal | 34 | 3 | 11.333 |
| jalr | 66 | 4 | 16.500 |
| shift (right, shamt 31) | 97 | 4 | 24.250 |

CPI ratio over all mixes: [8.75, 24.25]  (min at 100% store, max at 100% shift (right, shamt 31))
