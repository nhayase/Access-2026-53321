Formal equivalence proofs of the synthesis flow (m2d/pdk2d/formal.py, tools/prove_flow.py).

map: primitive (yosys) == mapped; legalize: mapped == fan-out-legalized; pipeline: legalized (one evaluation) == depth-compliant physical netlist over S periods for all architectural states, pipeline contents and environment garbage.  'hash' = outputs whose AIG literals coincide after structural hashing, 'SAT' = outputs proved by CaDiCaL.  Negative controls: the S - 1 ring must fail the pipeline proof; random single-cell mutants must fail the map proof.

| W | adder | T | outputs | map hash/SAT | legalize hash/SAT | S | T_c | pipeline | S-1 fails | mutants detected | s |
|--:|:--|--:|--:|:--|:--|--:|--:|:--:|:--:|:--:|--:|
| 1 | ripple | 10474 | 268 | 223/45 | 268/0 | 2 | 15500 | PROVED | yes | 20/20 | 1.3 |
| 2 | ripple | 15705 | 262 | 251/11 | 262/0 | 3 | 27127 | PROVED | yes | 20/20 | 0.9 |
| 4 | ripple | 16359 | 262 | 249/13 | 262/0 | 3 | 31703 | PROVED | yes | 20/20 | 1.5 |
| 8 | ripple | 17748 | 264 | 247/17 | 264/0 | 4 | 38565 | PROVED | yes | 20/20 | 1.1 |
| 16 | ripple | 20649 | 270 | 245/25 | 270/0 | 5 | 57447 | PROVED | yes | 20/20 | 2.1 |
| 32 | ripple | 25679 | 284 | 180/104 | 284/0 | 8 | 98448 | PROVED | yes | 20/20 | 2.5 |
| 8 | prefix | 17979 | 264 | 242/22 | 264/0 | 3 | 34341 | PROVED | yes | 20/20 | 1.2 |
| 16 | prefix | 21327 | 270 | 200/70 | 270/0 | 3 | 41830 | PROVED | yes | 20/20 | 2.2 |
| 32 | prefix | 27195 | 284 | 176/108 | 284/0 | 4 | 55960 | PROVED | yes | 20/20 | 4.0 |
