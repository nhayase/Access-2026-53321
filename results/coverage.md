Design-point x validation-stage coverage (generated).

co-sim     RTL co-simulation tests against the golden ISS
equiv      formal (SAT) combinational equivalence after mapping and
           again after fan-out legalization (results/formal.md), plus
           randomized equivalence over 8,192 patterns
kernel CPI cycle-accurate RTL run of the five hand kernels, result
           asserted against the ISS (repeated with 3 wait states)
gate-level execution of one complete program (checksum) on the
           mapped netlist: cycles asserted = RTL, result asserted = ISS
compiled   prefix of a compiled Embench-IoT binary executed at RTL:
           cycles = closed-form model, whole data memory = ISS
ABC        independent yosys+ABC mapping of the same RTLIL
pipelined  depth-compliant (<= 17 stages) physical netlist: DRC PASS,
           formal one-cycle equivalence over S periods (results/formal.md)
           and randomized (4,096 cases), gate-level
           execution of checksum at sub-cycle granularity with cycles = RTL,
           result = ISS (results/depth_compliant.md)

| design point | co-sim | equiv | kernel CPI | gate-level | compiled | ABC | pipelined |
|:--|--:|:--:|:--:|:--:|:--:|:--:|:--:|
| W = 1 ripple | 12 | yes | yes | yes | yes | yes | yes |
| W = 2 ripple | 11 | yes | yes | yes | yes | not run | yes |
| W = 4 ripple | 11 | yes | yes | yes | yes | not run | yes |
| W = 8 ripple | 11 | yes | yes | yes | yes | not run | yes |
| W = 16 ripple | 11 | yes | yes | yes | yes | not run | yes |
| W = 32 ripple | 11 | yes | yes | yes | yes | yes | yes |
| W = 8 prefix | 11 | yes | yes | yes | yes | not run | yes |
| W = 16 prefix | 11 | yes | yes | yes | yes | not run | yes |
| W = 32 prefix | 11 | yes | yes | yes | yes | yes | yes |

122 co-simulation tests over 11 (width, adder) pairs.
Two stages are deliberately partial and are marked as such: gate-level
execution is one program per netlist, and the independent mapper is run
for three representative netlists.
