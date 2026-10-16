Independent-mapper cross-check: yosys+ABC (built-in gate classes with a 1:1 library correspondence), translated cell-for-cell into 2D_NMOS_lib and analyzed with the same transistor/delay model.  ABC optimizes gate count, not transistors, and does not enforce the fan-out <= 4 rule, so each ABC netlist is reported BOTH as ABC emits it and after the SAME even-level inverter-tree legalization pass that every netlist of this flow passes through.  The legalized rows are the like-for-like comparison: they satisfy the same design rule and their delays are no longer optimistic lower bounds.

| design | mapper | cells | T (NMOS) | depth | delay us | max fan-out | nets > 4 |
|:--|:--|--:|--:|--:|--:|--:|--:|
| m2d_w1_ripple | yosys+ABC (as emitted) | 851 | 6490 | 15 | 120.5 | 40 | 61 |
| m2d_w1_ripple | yosys+ABC (fan-out legalized) | 1134 | 7056 | 23 | 175.4 | 4 | 0 |
| m2d_w32_ripple | yosys+ABC (as emitted) | 2821 | 15718 | 60 | 474.2 | 84 | 214 |
| m2d_w32_ripple | yosys+ABC (fan-out legalized) | 3894 | 17864 | 74 | 570.0 | 4 | 0 |
| m2d_w32_prefix | yosys+ABC (as emitted) | 2616 | 15326 | 40 | 309.0 | 71 | 170 |
| m2d_w32_prefix | yosys+ABC (fan-out legalized) | 3536 | 17166 | 50 | 384.5 | 4 | 0 |

Every legalized netlist above was re-verified against the netlist ABC emitted by randomized functional equivalence over 8,192 patterns at all primary outputs and flip-flop data inputs.

NOTE on the 'as emitted' rows: the stage-delay model saturates the load at the legal maximum of 4 pins (see pdk2d/cells.py:stage_delay_us), because the 171 us anchor of Ao et al. is quoted at maximum legal fan-out.  Those netlists violate the fan-out rule, so their delay column is an OPTIMISTIC lower bound and is retained only to show what the unconstrained mapper produces.  All QoR factors q quoted in the article are computed from the LEGALIZED rows.
