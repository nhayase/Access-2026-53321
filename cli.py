"""Command-line interface of M2D.

    python3 cli.py generate [-t il|v] [FILE]   emit RTLIL / Verilog
    python3 cli.py synth    [-o DIR] [--pipeline]  run the full 2D synthesis flow
                            (--pipeline: also the depth-compliant physical netlist)
    python3 cli.py selftest                    run the co-simulation test suite
    python3 cli.py study    [--quick]          the full design-space sweep
    python3 cli.py embench  [--elf-dir DIR]    compiled-workload analysis
    python3 cli.py coverage                    validation coverage matrix
"""

import argparse
import sys

from amaranth.back import rtlil, verilog

from m2d.core import M2D


__all__ = ["main"]


def _mk(args):
    return M2D(width=args.width, adder=args.adder,
               reset_address=args.reset_addr)


def _cmd_generate(args):
    cpu = _mk(args)
    kind = args.type
    if kind is None and args.file is not None:
        if args.file.name.endswith(".il"):
            kind = "il"
        elif args.file.name.endswith(".v"):
            kind = "v"
    if kind is None:
        kind = "il"
    if kind == "il":
        output = rtlil.convert(cpu, name="m2d")
    else:
        output = verilog.convert(cpu, name="m2d")
    (args.file or sys.stdout).write(output)


def _cmd_synth(args):
    from m2d.pdk2d import synthesize, format_report

    cpu = _mk(args)
    flow = synthesize(cpu, name="m2d", build_dir=args.output)
    report = format_report(flow.result)
    path = f"{args.output}/m2d_report.txt"
    with open(path, "w") as f:
        f.write(report)
    print()
    print(report)
    print(f"[pdk2d] report written to {path}")
    from m2d.pdk2d.cells import CONSTRAINTS
    nm_ok = flow.result.min_noise_margin >= CONSTRAINTS.min_noise_margin
    rc = 0 if (flow.result.fanout_ok and nm_ok) else 1
    if args.pipeline:
        pres = flow.pipeline()
        report = format_report(pres)
        path = f"{args.output}/m2d_pipelined_report.txt"
        with open(path, "w") as f:
            f.write(report)
        print()
        print(report)
        print(f"[pdk2d] report of the depth-compliant physical netlist "
              f"written to {path}")
        nm_ok = pres.min_noise_margin >= CONSTRAINTS.min_noise_margin
        rc = max(rc, 0 if (pres.depth_ok and pres.fanout_ok and nm_ok)
                 else 1)
    return rc


def _cmd_embench(args):
    """Compiled workloads: mixes, the mix envelope and RTL spot checks."""
    import glob
    import study

    print(study.compiled_workloads(out_dir=args.output,
                                   elf_dir=args.elf_dir,
                                   refresh=args.refresh))
    print(study.mix_envelope(out_dir=args.output))
    if args.spot:
        elfs = sorted(glob.glob(f"{args.elf_dir}/*.elf"))
        picked = [e for e in elfs
                  if any(k in e for k in args.spot)] or elfs[:args.n_spot]
        if not picked:
            print("[embench] no ELF images for the RTL spot check; "
                  "run tools/build_embench.sh")
            return 0
        print(study.compiled_rtl_spot(picked, n_insns=args.spot_insns,
                                      out_dir=args.output))
    return 0


def _cmd_coverage(args):
    import study
    print(study.coverage_matrix(out_dir=args.output))
    return 0


def _cmd_selftest(args):
    import unittest
    suite = unittest.defaultTestLoader.discover("tests", top_level_dir=".")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


def _cmd_study(args):
    import study
    study.run(study.POINTS_QUICK if getattr(args, "quick", False)
              else study.POINTS_FULL)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="M2D: digit-serial RV32I design space "
                    "for MoS2 2D semiconductors")
    parser.add_argument("--reset-addr", type=lambda s: int(s, 16),
                        default="0x00000000", help="reset vector address")
    parser.add_argument("--width", type=int, default=1,
                        choices=[1, 2, 4, 8, 16, 32],
                        help="datapath digit width in bits")
    parser.add_argument("--adder", default="ripple",
                        choices=["ripple", "prefix"],
                        help="digit adder architecture (prefix = Brent-Kung)")
    sub = parser.add_subparsers(dest="action", required=True)

    p = sub.add_parser("generate", help="emit RTLIL or Verilog")
    p.add_argument("-t", "--type", choices=["il", "v"], default=None,
                   help="output language (default: from FILE extension)")
    p.add_argument("file", metavar="FILE", nargs="?",
                   type=argparse.FileType("w"), help="output file")

    p = sub.add_parser("synth",
                       help="yosys lowering + Python techmap for the MoS2 PDK")
    p.add_argument("-o", "--output", default="build", help="build directory")
    p.add_argument("--pipeline", action="store_true",
                   help="also build, verify and report the depth-compliant "
                        "(<= 17 stages) sub-cycle-pipelined physical netlist "
                        "(build/m2d_pipelined.json)")

    sub.add_parser("selftest", help="run the co-simulation test suite")

    p = sub.add_parser("study",
                       help="run the full design-space sweep (see study.py)")
    p.add_argument("--quick", action="store_true",
                   help="reduced design-point set")

    p = sub.add_parser("embench",
                       help="compiled-workload (Embench-IoT) analysis")
    p.add_argument("--elf-dir", default="embench",
                   help="directory of compiled RV32I .elf images "
                        "(tools/build_embench.sh)")
    p.add_argument("-o", "--output", default="results",
                   help="results directory")
    p.add_argument("--refresh", action="store_true",
                   help="re-trace the ELF images instead of using the "
                        "cached mixes")
    p.add_argument("--spot", nargs="*", default=None,
                   help="also run RTL spot checks; optional name filters")
    p.add_argument("--n-spot", type=int, default=4,
                   help="number of binaries to spot-check when no filter "
                        "is given")
    p.add_argument("--spot-insns", type=int, default=6000,
                   help="retired instructions per spot check")

    p = sub.add_parser("coverage",
                       help="regenerate the validation coverage matrix")
    p.add_argument("-o", "--output", default="results",
                   help="results directory")

    args = parser.parse_args(argv)

    ret = {"generate": _cmd_generate,
           "synth":    _cmd_synth,
           "selftest": _cmd_selftest,
           "study":    _cmd_study,
           "embench":  _cmd_embench,
           "coverage": _cmd_coverage}[args.action](args)
    sys.exit(ret or 0)


if __name__ == "__main__":
    main()
