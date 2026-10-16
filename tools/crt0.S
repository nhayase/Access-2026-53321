/* Bare-metal RV32I startup for the M2D compiled workloads.
 *
 * Flat image at address 0, so that the RTL memory bench (which resets the
 * core to PC = 0) and the golden ISS see the same entry point.  main()'s
 * return value is stored at word address 0x80 -- the slot that
 * study.golden_run() already reads -- and the program then spins on a
 * jump-to-self, which is the halt convention of both simulators.
 *
 * Embench main() returns !correct, so 0 at 0x80 means the benchmark's own
 * verify_benchmark() passed.
 */
    .section .text.init,"ax",@progbits
    .globl _start
_start:
    la      sp, _stack_top
    la      t0, __bss_start          /* zero .bss */
    la      t1, __bss_end
1:  bgeu    t0, t1, 2f
    sw      zero, 0(t0)
    addi    t0, t0, 4
    j       1b
2:  li      a0, 0
    li      a1, 0
    call    main
    li      t0, 0x80                 /* result slot read by the harness */
    sw      a0, 0(t0)
_halt:
    j       _halt                    /* jump-to-self halt */
