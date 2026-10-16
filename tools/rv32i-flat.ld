/* Flat single-region image for the M2D simulators: .text at 0, the result
 * slot at 0x80 kept clear of code, and a stack far above .bss.  Both
 * simulators use a sparse memory whose unmapped words read as zero, so the
 * only requirement is that nothing overlaps. */
OUTPUT_ARCH(riscv)
ENTRY(_start)
MEMORY { RAM (rwx) : ORIGIN = 0x00000000, LENGTH = 8M }
SECTIONS {
  . = 0x0;
  .text : {
    *(.text.init)
    . = 0x100;                       /* leave 0x80 free for the result word */
    *(.text*) *(.rodata*) *(.srodata*)
  } > RAM
  . = ALIGN(4);
  .data : { *(.data*) *(.sdata*) } > RAM
  . = ALIGN(4);
  __bss_start = .;
  .bss  : { *(.bss*) *(.sbss*) *(COMMON) } > RAM
  . = ALIGN(4);
  __bss_end = .;
  . = ALIGN(16);
  _end = .;
  . = 0x7F0000;
  _stack_top = .;
}
