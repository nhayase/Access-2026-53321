/* Embench board support for a core with no timer and no I/O: the harness
 * needs the three hooks to exist, and M2D measures cycles in the simulator
 * rather than in the program. */
#include <support.h>

void initialise_board (void) { }

void __attribute__ ((noinline)) start_trigger (void)
{ __asm__ volatile ("" ::: "memory"); }

void __attribute__ ((noinline)) stop_trigger (void)
{ __asm__ volatile ("" ::: "memory"); }
