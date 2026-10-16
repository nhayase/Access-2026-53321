Formal proofs for the integrated core-plus-register-file netlists (configuration B; tools/prove_rf_system.py).  Columns as in results/formal.md.

| W | adder | T_sys | outputs | map hash/SAT | legalize hash/SAT | S | T_sys,c | pipeline | S-1 fails | s |
|--:|:--|--:|--:|:--|:--|--:|--:|:--:|:--:|--:|
| 1 | ripple | 72869 | 1238 | 202/1036 | 1238/0 | 3 | 104581 | PROVED | yes | 44.5 |
| 2 | ripple | 74861 | 1232 | 232/1000 | 1232/0 | 3 | 114645 | PROVED | yes | 47.2 |
| 4 | ripple | 73939 | 1231 | 231/1000 | 1231/0 | 3 | 114079 | PROVED | yes | 91.5 |
| 8 | ripple | 75144 | 1230 | 230/1000 | 1230/0 | 4 | 128085 | PROVED | yes | 15.2 |
| 16 | ripple | 77468 | 1229 | 229/1000 | 1229/0 | 5 | 155112 | PROVED | yes | 25.7 |
| 32 | ripple | 82020 | 1228 | 165/1063 | 1228/0 | 8 | 212955 | PROVED | yes | 10.4 |
| 8 | prefix | 75379 | 1230 | 228/1002 | 1230/0 | 3 | 116402 | PROVED | yes | 91.4 |
| 16 | prefix | 78146 | 1229 | 184/1045 | 1229/0 | 3 | 123853 | PROVED | yes | 47.0 |
| 32 | prefix | 83540 | 1228 | 161/1067 | 1228/0 | 4 | 139817 | PROVED | yes | 14.6 |
