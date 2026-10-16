#!/usr/bin/env bash
# Build the compiled workloads used by study.compiled_workloads().
#
# Embench-IoT is cross-compiled for the RV32I subset that M2D implements and
# linked against the bare-metal runtime in tools/ below, so that each binary
# is a flat image starting at address 0 that ends in a jump-to-self halt --
# exactly the shape that tests.rv32.GoldenRV32I and study.measure_cycles
# already accept.  The result is a directory of .elf images:
#
#   tools/build_embench.sh [OUT_DIR]        (default: ./embench)
#   python3 cli.py embench --refresh --spot slre ud sglib qrduino
#
# Requirements (both external to this repository):
#   * a bare-metal RISC-V toolchain providing riscv-none-elf-gcc, e.g.
#     https://github.com/xpack-dev-tools/riscv-none-elf-gcc-xpack
#     (set RISCV_GCC to the binary if it is not on PATH)
#   * the Embench-IoT sources, https://github.com/embench/embench-iot
#     (set EMBENCH_SRC to the checkout; it is cloned here if absent)
#
# The measured mixes are cached in results/embench_mixes.json, so the tables
# regenerate without this script.  Run it only to reproduce them from source.
set -euo pipefail

OUT="${1:-embench}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GCC="${RISCV_GCC:-riscv-none-elf-gcc}"
SRC="${EMBENCH_SRC:-$HERE/embench-iot}"

command -v "$GCC" >/dev/null || { echo "no $GCC on PATH; set RISCV_GCC"; exit 1; }
[ -d "$SRC" ] || git clone --depth 1 https://github.com/embench/embench-iot "$SRC"

mkdir -p "$OUT"
CFLAGS=(
  -march=rv32i -mabi=ilp32 -mstrict-align      # no M/A/F/C: M2D is RV32I only
  -Os -ffreestanding -nostartfiles
  -DCPU_MHZ=1 -DWARMUP_HEAT=0 -DGLOBAL_SCALE_FACTOR=1
  -I"$SRC/support" -I"$HERE"
)

built=0 failed=()
for d in "$SRC"/src/*/; do
  b="$(basename "$d")"
  if "$GCC" "${CFLAGS[@]}" -I"$d" \
       "$HERE/crt0.S" "$HERE/boardsupport.c" \
       "$SRC/support/main.c" "$SRC/support/beebsc.c" "$d"/*.c \
       -T "$HERE/rv32i-flat.ld" -o "$OUT/$b.elf" \
       -lc -lgcc --specs=nano.specs --specs=nosys.specs 2>/dev/null
  then
    echo "  built  $b"; built=$((built + 1))
  else
    echo "  SKIP   $b (needs facilities outside the RV32I subset)"
    failed+=("$b"); rm -f "$OUT/$b.elf"
  fi
done

echo
echo "$built benchmarks in $OUT/ ; skipped: ${failed[*]:-none}"
echo "next:  python3 cli.py embench --elf-dir $OUT --refresh --spot slre ud"
