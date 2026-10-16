Model validation against RV32-WUJI (Ao et al., Nature 640, 654 (2025))

V1. Calibration anchors (delay / power / sequential cost).  NOTE: these are CALIBRATIONS, not independent validations -- the delay pair (t0, slope) is jointly fitted to the published 171 us total, so V1 carries no evidential weight on its own.  The validation anchors of this study are V2 (117/117 cycle-exact per-class checks, 13 classes x 9 design points), V2b (gate-level execution of full workloads, cycle count and checksum asserted against RTL and the golden ISS), and the yosys+ABC mapper cross-check.

| item | model | paper | type |
|:--|:--|:--|:--|
| 17-stage critical path | 171.02 us (17 x (4.06 + 0.6 x 10 pF)) | 171 us (Fig. 3c/d) | calibrated (jointly fitted) |
| static power | 5931 T x 72.67 nW/T = 0.431 mW | 0.431 mW (Ext. Table 2) | calibrated |
| flip-flop cost | 18 T/FF | 8-bit register = 144 T (Suppl. Fig. 7) | calibrated |
| excluded cells | 7 cells with NM < 0.2 V | Fig. 3b | input data |

V2. Per-instruction-class cycle counts (RTL differential measurement vs. closed-form serial model; D = 32/W)

| design point | class | measured | model | match |
|:--|:--|--:|--:|:--:|
| W=1/ripple | ADDI | 34.00 | 34 | OK |
| W=1/ripple | ADD | 34.00 | 34 | OK |
| W=1/ripple | LUI | 34.00 | 34 | OK |
| W=1/ripple | AUIPC | 34.00 | 34 | OK |
| W=1/ripple | SLT | 66.00 | 66 | OK |
| W=1/ripple | SLLI4 | 66.00 | 66 | OK |
| W=1/ripple | SRLI4 | 70.00 | 70 | OK |
| W=1/ripple | BEQ taken | 66.00 | 66 | OK |
| W=1/ripple | BNE n-t | 66.00 | 66 | OK |
| W=1/ripple | JAL | 34.00 | 34 | OK |
| W=1/ripple | JALR | 66.00 | 66 | OK |
| W=1/ripple | LW | 67.00 | 67 | OK |
| W=1/ripple | SW | 35.00 | 35 | OK |
| W=2/ripple | ADDI | 18.00 | 18 | OK |
| W=2/ripple | ADD | 18.00 | 18 | OK |
| W=2/ripple | LUI | 18.00 | 18 | OK |
| W=2/ripple | AUIPC | 18.00 | 18 | OK |
| W=2/ripple | SLT | 34.00 | 34 | OK |
| W=2/ripple | SLLI4 | 34.00 | 34 | OK |
| W=2/ripple | SRLI4 | 34.00 | 34 | OK |
| W=2/ripple | BEQ taken | 34.00 | 34 | OK |
| W=2/ripple | BNE n-t | 34.00 | 34 | OK |
| W=2/ripple | JAL | 18.00 | 18 | OK |
| W=2/ripple | JALR | 34.00 | 34 | OK |
| W=2/ripple | LW | 35.00 | 35 | OK |
| W=2/ripple | SW | 19.00 | 19 | OK |
| W=4/ripple | ADDI | 10.00 | 10 | OK |
| W=4/ripple | ADD | 10.00 | 10 | OK |
| W=4/ripple | LUI | 10.00 | 10 | OK |
| W=4/ripple | AUIPC | 10.00 | 10 | OK |
| W=4/ripple | SLT | 18.00 | 18 | OK |
| W=4/ripple | SLLI4 | 18.00 | 18 | OK |
| W=4/ripple | SRLI4 | 18.00 | 18 | OK |
| W=4/ripple | BEQ taken | 18.00 | 18 | OK |
| W=4/ripple | BNE n-t | 18.00 | 18 | OK |
| W=4/ripple | JAL | 10.00 | 10 | OK |
| W=4/ripple | JALR | 18.00 | 18 | OK |
| W=4/ripple | LW | 19.00 | 19 | OK |
| W=4/ripple | SW | 11.00 | 11 | OK |
| W=8/ripple | ADDI | 6.00 | 6 | OK |
| W=8/ripple | ADD | 6.00 | 6 | OK |
| W=8/ripple | LUI | 6.00 | 6 | OK |
| W=8/ripple | AUIPC | 6.00 | 6 | OK |
| W=8/ripple | SLT | 10.00 | 10 | OK |
| W=8/ripple | SLLI4 | 10.00 | 10 | OK |
| W=8/ripple | SRLI4 | 10.00 | 10 | OK |
| W=8/ripple | BEQ taken | 10.00 | 10 | OK |
| W=8/ripple | BNE n-t | 10.00 | 10 | OK |
| W=8/ripple | JAL | 6.00 | 6 | OK |
| W=8/ripple | JALR | 10.00 | 10 | OK |
| W=8/ripple | LW | 11.00 | 11 | OK |
| W=8/ripple | SW | 7.00 | 7 | OK |
| W=16/ripple | ADDI | 4.00 | 4 | OK |
| W=16/ripple | ADD | 4.00 | 4 | OK |
| W=16/ripple | LUI | 4.00 | 4 | OK |
| W=16/ripple | AUIPC | 4.00 | 4 | OK |
| W=16/ripple | SLT | 6.00 | 6 | OK |
| W=16/ripple | SLLI4 | 6.00 | 6 | OK |
| W=16/ripple | SRLI4 | 6.00 | 6 | OK |
| W=16/ripple | BEQ taken | 6.00 | 6 | OK |
| W=16/ripple | BNE n-t | 6.00 | 6 | OK |
| W=16/ripple | JAL | 4.00 | 4 | OK |
| W=16/ripple | JALR | 6.00 | 6 | OK |
| W=16/ripple | LW | 7.00 | 7 | OK |
| W=16/ripple | SW | 5.00 | 5 | OK |
| W=32/ripple | ADDI | 3.00 | 3 | OK |
| W=32/ripple | ADD | 3.00 | 3 | OK |
| W=32/ripple | LUI | 3.00 | 3 | OK |
| W=32/ripple | AUIPC | 3.00 | 3 | OK |
| W=32/ripple | SLT | 4.00 | 4 | OK |
| W=32/ripple | SLLI4 | 4.00 | 4 | OK |
| W=32/ripple | SRLI4 | 4.00 | 4 | OK |
| W=32/ripple | BEQ taken | 4.00 | 4 | OK |
| W=32/ripple | BNE n-t | 4.00 | 4 | OK |
| W=32/ripple | JAL | 3.00 | 3 | OK |
| W=32/ripple | JALR | 4.00 | 4 | OK |
| W=32/ripple | LW | 5.00 | 5 | OK |
| W=32/ripple | SW | 4.00 | 4 | OK |
| W=8/prefix | ADDI | 6.00 | 6 | OK |
| W=8/prefix | ADD | 6.00 | 6 | OK |
| W=8/prefix | LUI | 6.00 | 6 | OK |
| W=8/prefix | AUIPC | 6.00 | 6 | OK |
| W=8/prefix | SLT | 10.00 | 10 | OK |
| W=8/prefix | SLLI4 | 10.00 | 10 | OK |
| W=8/prefix | SRLI4 | 10.00 | 10 | OK |
| W=8/prefix | BEQ taken | 10.00 | 10 | OK |
| W=8/prefix | BNE n-t | 10.00 | 10 | OK |
| W=8/prefix | JAL | 6.00 | 6 | OK |
| W=8/prefix | JALR | 10.00 | 10 | OK |
| W=8/prefix | LW | 11.00 | 11 | OK |
| W=8/prefix | SW | 7.00 | 7 | OK |
| W=16/prefix | ADDI | 4.00 | 4 | OK |
| W=16/prefix | ADD | 4.00 | 4 | OK |
| W=16/prefix | LUI | 4.00 | 4 | OK |
| W=16/prefix | AUIPC | 4.00 | 4 | OK |
| W=16/prefix | SLT | 6.00 | 6 | OK |
| W=16/prefix | SLLI4 | 6.00 | 6 | OK |
| W=16/prefix | SRLI4 | 6.00 | 6 | OK |
| W=16/prefix | BEQ taken | 6.00 | 6 | OK |
| W=16/prefix | BNE n-t | 6.00 | 6 | OK |
| W=16/prefix | JAL | 4.00 | 4 | OK |
| W=16/prefix | JALR | 6.00 | 6 | OK |
| W=16/prefix | LW | 7.00 | 7 | OK |
| W=16/prefix | SW | 5.00 | 5 | OK |
| W=32/prefix | ADDI | 3.00 | 3 | OK |
| W=32/prefix | ADD | 3.00 | 3 | OK |
| W=32/prefix | LUI | 3.00 | 3 | OK |
| W=32/prefix | AUIPC | 3.00 | 3 | OK |
| W=32/prefix | SLT | 4.00 | 4 | OK |
| W=32/prefix | SLLI4 | 4.00 | 4 | OK |
| W=32/prefix | SRLI4 | 4.00 | 4 | OK |
| W=32/prefix | BEQ taken | 4.00 | 4 | OK |
| W=32/prefix | BNE n-t | 4.00 | 4 | OK |
| W=32/prefix | JAL | 3.00 | 3 | OK |
| W=32/prefix | JALR | 4.00 | 4 | OK |
| W=32/prefix | LW | 5.00 | 5 | OK |
| W=32/prefix | SW | 4.00 | 4 | OK |

V3. Transistor accounting, W = 1 core vs. fabricated RV32-WUJI

| component | transistors | share |
|:--|--:|--:|
| flip-flops (18 T each) | 2610 | 24.9 % |
| fan-out buffer inverters (442 INV) | 884 | 8.4 % |
| MUX2 trees (imm/PC selects, FSM D-muxes) | 3249 | 31.0 % |
| other combinational logic | 3731 | 35.6 % |
| TOTAL (this flow) | 10474 | 100.0 % |
| RV32-WUJI whole chip (reference) | 5931 | -- |

Gap drivers vs. the fabricated chip (x1.77): no ABC-class global restructuring, 32:1 immediate-mux tree instead of the paper's serial immediate decoder, no register-file port sharing, FSM multi-writer D-input mux chains.
