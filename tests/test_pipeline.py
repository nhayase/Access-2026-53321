"""Tests of the depth-compliant sub-cycle pipelining (m2d/pdk2d/pipeline.py).

Two design points are synthesized, pipelined into <= 17-stage physical
netlists and checked by (i) the DRC/timing analyzer, (ii) the S-period
sequential equivalence check against the mapped netlist, (iii) the same
check with S-1 periods, which must fail, and (iv) a complete workload
executed at gate level at sub-cycle granularity, whose architectural
cycle count must equal the RTL and whose result must equal the golden
ISS.  The cut placement and the JSON round trip of netlists are tested
on their own.
"""

import itertools
import os
import random
import shutil
import tempfile
import unittest

from m2d.core import M2D
from m2d.pdk2d import (synthesize, analyze, subcycle_pipeline,
                       verify_subcycle, read_ports, read_mapped_json,
                       write_netlist_json, CONSTRAINTS)
from m2d.pdk2d.pipeline import _place_cuts


class TestSubcyclePipeline(unittest.TestCase):
    COSIM = False                 # not a co-simulation test (coverage.md)
    POINTS = ((1, "ripple"), (8, "prefix"))
    _flows = {}

    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.mkdtemp(prefix="m2d_pipeline_")
        for width, adder in cls.POINTS:
            tag = f"m2d_w{width}_{adder}"
            flow = synthesize(M2D(width=width, adder=adder), name=tag,
                              build_dir=cls.build, verify=False)
            ports = read_ports(os.path.join(cls.build, f"{tag}_gates.json"),
                               tag)
            cls._flows[(width, adder)] = (flow, ports)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.build, ignore_errors=True)

    def _pipelined(self, width, adder):
        flow, ports = self._flows[(width, adder)]
        pres = subcycle_pipeline(flow.mapped, ports)
        return flow, ports, pres

    def _check_point(self, width, adder):
        flow, ports, pres = self._pipelined(width, adder)
        res = analyze(pres.netlist)
        dmax = CONSTRAINTS.max_logic_depth
        self.assertLessEqual(res.logic_depth, dmax)
        self.assertTrue(res.depth_ok)
        self.assertTrue(res.fanout_ok)
        self.assertGreaterEqual(res.min_noise_margin,
                                CONSTRAINTS.min_noise_margin)
        self.assertEqual(pres.subcycles, -(-pres.endpoint_level // dmax))
        self.assertEqual(len(pres.cuts), pres.subcycles - 1)
        # sequential equivalence over S periods
        n = verify_subcycle(flow.mapped, pres, ports, patterns=1024)
        self.assertEqual(n, 1024)
        # ... and S-1 periods are not enough
        short = subcycle_pipeline(flow.mapped, ports,
                                  force_subcycles=pres.subcycles - 1)
        self.assertEqual(short.subcycles, pres.subcycles - 1)
        with self.assertRaises(AssertionError):
            verify_subcycle(flow.mapped, short, ports, patterns=256)
        return flow, ports, pres

    def _check_workload(self, width, adder, pres, workload="memcpy"):
        import study
        from tests.rv32 import M32
        arch, phys, alpha, io_pi, got = study.gate_level_sim_pipelined(
            pres, width, adder, workload=workload, build_dir=self.build)
        prog, data = study.WORKLOADS[workload]()
        n_insns, ref = study.golden_run(prog, dict(data))[:2]
        rtl, _ = study.measure_cycles(prog, data, n_insns, width, adder)
        self.assertEqual(arch, rtl)
        self.assertEqual(got & M32, ref & M32)
        self.assertEqual(phys, arch * pres.subcycles + pres.subcycles - 1)
        self.assertGreater(alpha, 0.0)

    def test_w1_ripple(self):
        flow, ports, pres = self._check_point(1, "ripple")
        self.assertEqual(pres.subcycles, 2)
        self._check_workload(1, "ripple", pres)

    def test_w8_prefix(self):
        flow, ports, pres = self._check_point(8, "prefix")
        self.assertEqual(pres.subcycles, 3)
        self._check_workload(8, "prefix", pres)

    def test_holdless_optional(self):
        flow, ports = self._flows[(1, "ripple")]
        pres = subcycle_pipeline(flow.mapped, ports, holdless=False)
        self.assertEqual(pres.n_holdless, 0)
        self.assertEqual(pres.n_hold_mux, len(pres.arch_ffs))
        res = analyze(pres.netlist)
        self.assertTrue(res.depth_ok and res.fanout_ok)
        verify_subcycle(flow.mapped, pres, ports, patterns=512)

    def test_netlist_json_round_trip(self):
        flow, ports = self._flows[(1, "ripple")]
        path = os.path.join(self.build, "roundtrip.json")
        write_netlist_json(flow.mapped, path)
        back = read_mapped_json(path)
        key = lambda g: (g[0], tuple(map(str, g[1])), str(g[2]), str(g[3]))
        self.assertEqual(sorted(map(key, flow.mapped.gates.values())),
                         sorted(map(key, back.gates.values())))
        self.assertEqual(flow.mapped.inputs, back.inputs)
        self.assertEqual(flow.mapped.outputs, back.outputs)
        self.assertEqual(flow.mapped.clocks, back.clocks)
        pres_a = subcycle_pipeline(flow.mapped, ports)
        pres_b = subcycle_pipeline(back, ports)
        self.assertEqual(pres_a.notes[0], pres_b.notes[0])
        self.assertEqual(analyze(pres_a.netlist).transistors,
                         analyze(pres_b.netlist).transistors)


class TestCutPlacement(unittest.TestCase):
    COSIM = False

    @staticmethod
    def _cost(span, cuts):
        return sum(1 for dl, lm in span.values()
                   for c in cuts if dl <= c <= lm - 1)

    @staticmethod
    def _admissible(cuts, S, dmax, l_end):
        if len(cuts) != S - 1:
            return False
        prev = 0
        for k, c in enumerate(cuts, 1):
            if not (prev < c <= min(prev + dmax, k * dmax)):
                return False
            prev = c
        return l_end - prev <= dmax

    def test_optimal_against_brute_force(self):
        rng = random.Random(7)
        dmax = 5
        for trial in range(40):
            l_end = rng.randint(6, 22)
            S = -(-l_end // dmax)
            span = {}
            for i in range(rng.randint(5, 40)):
                dl = rng.randint(0, l_end - 1)
                lm = rng.randint(dl + 1, l_end)
                span[i] = (dl, lm)
            cuts = _place_cuts(span, S, dmax, l_end)
            self.assertTrue(self._admissible(cuts, S, dmax, l_end),
                            (cuts, S, dmax, l_end))
            best = min((self._cost(span, c), c)
                       for c in itertools.combinations(range(1, l_end), S - 1)
                       if self._admissible(c, S, dmax, l_end))
            self.assertEqual(self._cost(span, cuts), best[0], (cuts, best))

    def test_single_band(self):
        self.assertEqual(_place_cuts({0: (0, 3)}, 1, 17, 12), [])


if __name__ == "__main__":
    unittest.main()
