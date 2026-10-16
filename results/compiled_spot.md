Compiled-code RTL spot checks.

The first N retired instructions of a compiled Embench-IoT binary are
executed on the RTL core at every design point.  `cycles` is measured,
`model` is model_cycles() on the mix of exactly those N instructions, and
`state` compares the whole data memory against the golden ISS.

| binary | N | design point | cycles | CPI | model | err | state |
|:--|--:|:--|--:|--:|--:|--:|:--:|
| slre.elf | 6000 | W=1 ripple | 287986 | 48.00 | 287986 | +0.0000 | OK |
| slre.elf | 6000 | W=2 ripple | 150994 | 25.17 | 150994 | +0.0000 | OK |
| slre.elf | 6000 | W=4 ripple | 82498 | 13.75 | 82498 | +0.0000 | OK |
| slre.elf | 6000 | W=8 ripple | 48250 | 8.04 | 48250 | +0.0000 | OK |
| slre.elf | 6000 | W=16 ripple | 31126 | 5.19 | 31126 | +0.0000 | OK |
| slre.elf | 6000 | W=32 ripple | 22564 | 3.76 | 22564 | +0.0000 | OK |
| slre.elf | 6000 | W=8 prefix | 48250 | 8.04 | 48250 | +0.0000 | OK |
| slre.elf | 6000 | W=16 prefix | 31126 | 5.19 | 31126 | +0.0000 | OK |
| slre.elf | 6000 | W=32 prefix | 22564 | 3.76 | 22564 | +0.0000 | OK |
| ud.elf | 6000 | W=1 ripple | 286994 | 47.83 | 286994 | +0.0000 | OK |
| ud.elf | 6000 | W=2 ripple | 149951 | 24.99 | 149951 | +0.0000 | OK |
| ud.elf | 6000 | W=4 ripple | 81583 | 13.60 | 81583 | +0.0000 | OK |
| ud.elf | 6000 | W=8 ripple | 47399 | 7.90 | 47399 | +0.0000 | OK |
| ud.elf | 6000 | W=16 ripple | 30307 | 5.05 | 30307 | +0.0000 | OK |
| ud.elf | 6000 | W=32 ripple | 21761 | 3.63 | 21761 | +0.0000 | OK |
| ud.elf | 6000 | W=8 prefix | 47399 | 7.90 | 47399 | +0.0000 | OK |
| ud.elf | 6000 | W=16 prefix | 30307 | 5.05 | 30307 | +0.0000 | OK |
| ud.elf | 6000 | W=32 prefix | 21761 | 3.63 | 21761 | +0.0000 | OK |
| sglib-combined.elf | 6000 | W=1 ripple | 253467 | 42.24 | 253467 | +0.0000 | OK |
| sglib-combined.elf | 6000 | W=2 ripple | 133483 | 22.25 | 133483 | +0.0000 | OK |
| sglib-combined.elf | 6000 | W=4 ripple | 73491 | 12.25 | 73491 | +0.0000 | OK |
| sglib-combined.elf | 6000 | W=8 ripple | 43495 | 7.25 | 43495 | +0.0000 | OK |
| sglib-combined.elf | 6000 | W=16 ripple | 28497 | 4.75 | 28497 | +0.0000 | OK |
| sglib-combined.elf | 6000 | W=32 ripple | 20998 | 3.50 | 20998 | +0.0000 | OK |
| sglib-combined.elf | 6000 | W=8 prefix | 43495 | 7.25 | 43495 | +0.0000 | OK |
| sglib-combined.elf | 6000 | W=16 prefix | 28497 | 4.75 | 28497 | +0.0000 | OK |
| sglib-combined.elf | 6000 | W=32 prefix | 20998 | 3.50 | 20998 | +0.0000 | OK |
| qrduino.elf | 6000 | W=1 ripple | 253467 | 42.24 | 253467 | +0.0000 | OK |
| qrduino.elf | 6000 | W=2 ripple | 133483 | 22.25 | 133483 | +0.0000 | OK |
| qrduino.elf | 6000 | W=4 ripple | 73491 | 12.25 | 73491 | +0.0000 | OK |
| qrduino.elf | 6000 | W=8 ripple | 43495 | 7.25 | 43495 | +0.0000 | OK |
| qrduino.elf | 6000 | W=16 ripple | 28497 | 4.75 | 28497 | +0.0000 | OK |
| qrduino.elf | 6000 | W=32 ripple | 20998 | 3.50 | 20998 | +0.0000 | OK |
| qrduino.elf | 6000 | W=8 prefix | 43495 | 7.25 | 43495 | +0.0000 | OK |
| qrduino.elf | 6000 | W=16 prefix | 28497 | 4.75 | 28497 | +0.0000 | OK |
| qrduino.elf | 6000 | W=32 prefix | 20998 | 3.50 | 20998 | +0.0000 | OK |

36 of 36 runs match at zero tolerance.
