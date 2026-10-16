"""Formal equivalence proofs of the synthesis flow at W = 1 ripple
(m2d/pdk2d/formal.py): mapping, fan-out legalization and sub-cycle
pipelining are proved; the S - 1 ring and single-cell mutants are refuted."""
import os
import unittest

from m2d.core import M2D
from m2d.pdk2d import synthesize, read_mapped_json
from m2d.pdk2d.techmap import read_yosys_json, techmap
from m2d.pdk2d.pipeline import subcycle_pipeline, read_ports
from m2d.pdk2d.formal import prove_comb_equivalent, prove_subcycle

BUILD = os.environ.get("M2D_BUILD", "build")
TAG = "m2d_w1_ripple"


def _netlists():
    gates = os.path.join(BUILD, f"{TAG}_gates.json")
    legal = os.path.join(BUILD, f"{TAG}_mapped.json")
    if not (os.path.exists(gates) and os.path.exists(legal)):
        synthesize(M2D(width=1, adder="ripple"), name=TAG, build_dir=BUILD,
                   verify=False)
    gnet = read_yosys_json(gates, top=TAG)
    return gnet, techmap(gnet), read_mapped_json(legal), read_ports(gates, TAG)


class FormalW1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gnet, cls.mapped, cls.legal, cls.ports = _netlists()

    def test_mapping_and_legalization_proved(self):
        prove_comb_equivalent(self.gnet, self.mapped)
        prove_comb_equivalent(self.mapped, self.legal)

    def test_mutant_refuted(self):
        mm = self.mapped.copy()
        swap = {"NAND2": "NOR2", "NOR2": "NAND2", "AOI21": "OAI21",
                "OAI21": "AOI21", "AND2": "OR2", "OR2": "AND2"}
        gid = next(g for g, v in mm.gates.items() if v[0] in swap)
        mm.gates[gid][0] = swap[mm.gates[gid][0]]
        with self.assertRaises(AssertionError):
            prove_comb_equivalent(self.gnet, mm)

    def test_pipeline_proved_and_short_ring_refuted(self):
        pres = subcycle_pipeline(self.legal, self.ports)
        self.assertEqual(pres.subcycles, 2)
        self.assertEqual(pres.netlist.transistors(), 15500)
        prove_subcycle(self.legal, pres, self.ports)
        short = subcycle_pipeline(self.legal, self.ports, force_subcycles=1)
        with self.assertRaises(AssertionError):
            prove_subcycle(self.legal, short, self.ports)


if __name__ == "__main__":
    unittest.main()
