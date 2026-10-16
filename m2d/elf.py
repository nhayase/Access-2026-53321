"""Minimal ELF32 little-endian loader for RV32I program images.

Only what M2D needs: turn the PT_LOAD segments of a statically linked,
bare-metal ELF into the sparse ``{word_address: word}`` dictionary that both
the golden ISS (``tests.rv32.GoldenRV32I``) and the RTL memory bench
(``study.measure_cycles``) already speak.  No relocation, no dynamic
linking, no section-header parsing.

This exists so that COMPILED workloads -- Embench-IoT built with a
bare-metal RISC-V GCC -- can be run on exactly the same models as the
hand-assembled kernels of ``study.WORKLOADS``.  See ``study.trace_elf``.
"""

import struct

__all__ = ["load_elf", "ElfError"]

_PT_LOAD = 1


class ElfError(ValueError):
    pass


def load_elf(path):
    """Return ``(mem, entry)``.

    ``mem`` maps word address (byte address >> 2) to a 32-bit little-endian
    word; ``entry`` is the byte address of the entry point.  Bytes in a
    segment beyond ``p_filesz`` (i.e. ``.bss``) are materialized as zero so
    that a simulator with a sparse, zero-default memory and one with a dense
    memory agree.
    """
    raw = open(path, "rb").read()
    if raw[:4] != b"\x7fELF":
        raise ElfError(f"{path}: not an ELF file")
    if raw[4] != 1 or raw[5] != 1:
        raise ElfError(f"{path}: not ELF32 little-endian")
    (e_entry, e_phoff, _e_shoff, _e_flags,
     _e_ehsize, e_phentsize, e_phnum) = struct.unpack_from("<IIIIHHH", raw, 24)

    mem = {}
    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        (p_type, p_offset, p_vaddr, _p_paddr,
         p_filesz, p_memsz, _p_flags, _p_align) = struct.unpack_from(
            "<IIIIIIII", raw, off)
        if p_type != _PT_LOAD:
            continue
        if p_vaddr & 3:
            raise ElfError(f"{path}: PT_LOAD at unaligned vaddr {p_vaddr:#x}")
        for a in range(0, p_memsz, 4):
            if a < p_filesz:
                chunk = raw[p_offset + a:p_offset + a + 4].ljust(4, b"\0")
                word = struct.unpack("<I", chunk)[0]
            else:
                word = 0
            mem[(p_vaddr + a) >> 2] = word
    if not mem:
        raise ElfError(f"{path}: no PT_LOAD segments")
    return mem, e_entry
