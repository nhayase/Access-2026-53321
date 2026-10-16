"""Digit adders for M2D.

Two architectures, selectable per core instance:

  * ``ripple``:  *structural* chain of W full adders, written out gate by
    gate (O(W) carry stages, minimum transistor count).  A behavioural
    ``a + b + cin`` must NOT be used: yosys lowers ``$add`` through
    ``$alu``/``$lcu`` into a parallel-prefix carry network, which would
    silently turn the "ripple" design points into prefix adders and void
    the comparison this study exists to make.
  * ``prefix``:  structural Brent-Kung parallel-prefix adder
    (O(log W) stages).  Brent-Kung is chosen over Sklansky / Kogge-Stone
    because its prefix *network* has a maximum node fan-out of 2, against
    W/2 at the Sklansky root, so it needs far less buffering under the
    fan-out <= 4 design rule of the MoS2 2D process.  Note that the final
    carry stage c[i] = G[i-1] | (P[i-1] & cin) distributes ``cin`` to W
    gates, so the adder as a whole is NOT fan-out-4 clean by construction;
    the flow's fan-out legalization handles that net like any other, and
    the resulting buffer inverters are counted in the reported area/depth.

Both return ``(sum[W], carry_out)`` and are functionally identical; the
prefix variant exists to answer the question whether *parallel* carry
computation pays off under the 2D depth/fan-out constraints.
"""

from amaranth import *


__all__ = ["make_adder", "ADDER_KINDS"]

ADDER_KINDS = ("ripple", "prefix")


def make_adder(m, kind, a, b, cin, name):
    """Instantiate a W-bit adder; returns (sum W bits, carry_out 1 bit)."""
    w = len(a)
    assert len(b) == w
    s    = Signal(w, name=f"{name}_s")
    cout = Signal(name=f"{name}_co")
    if kind == "ripple" or w == 1:
        # *Structural* ripple-carry chain of full adders.  A behavioural
        # ``a + b + cin`` must not be used here: yosys' default techmap
        # lowers ``$add`` through ``$alu``/``$lcu`` into a parallel-prefix
        # (log-depth) carry network, which would silently turn the "ripple"
        # design points into prefix adders and void the comparison.
        c = cin
        bits = []
        for i in range(w):
            si = Signal(name=f"{name}_s{i}")
            m.d.comb += si.eq(a[i] ^ b[i] ^ c)
            bits.append(si)
            if i < w - 1 or True:
                ci = Signal(name=f"{name}_c{i + 1}")
                m.d.comb += ci.eq((a[i] & b[i]) | (a[i] & c) | (b[i] & c))
                c = ci
        m.d.comb += [s.eq(Cat(*bits)), cout.eq(c)]
        return s, cout
    if kind != "prefix":
        raise ValueError(f"unknown adder kind {kind!r}")
    assert w & (w - 1) == 0, "prefix adder requires a power-of-two width"

    # bitwise generate / propagate
    g = Signal(w, name=f"{name}_g")
    p = Signal(w, name=f"{name}_p")
    m.d.comb += [g.eq(a & b), p.eq(a ^ b)]

    # Brent-Kung prefix network over (G, P); node i holds the group
    # (generate, propagate) of some range ending at bit i.  After the
    # up-sweep and down-sweep, node i covers [0..i].
    G = [g[i] for i in range(w)]
    P = [p[i] for i in range(w)]

    def combine(hi, lo, tag):
        """(G,P)[hi] (o) (G,P)[lo]  ->  new signals for node hi."""
        ng = Signal(name=f"{name}_G{tag}")
        np_ = Signal(name=f"{name}_P{tag}")
        m.d.comb += [
            ng .eq(G[hi] | (P[hi] & G[lo])),
            np_.eq(P[hi] & P[lo]),
        ]
        G[hi], P[hi] = ng, np_

    # up-sweep: distances 1, 2, 4, ... w/2
    d = 1
    while d < w:
        for i in range(2 * d - 1, w, 2 * d):
            combine(i, i - d, f"u{d}_{i}")
        d *= 2
    # down-sweep: distances w/4, ... 1
    d = w // 4
    while d and d >= 1:
        for i in range(3 * d - 1, w, 2 * d):
            combine(i, i - d, f"d{d}_{i}")
        d //= 2

    # carries: c[0] = cin, c[i] = G[0..i-1] | P[0..i-1] & cin
    c = [None] * (w + 1)
    c[0] = cin
    for i in range(1, w + 1):
        ci = Signal(name=f"{name}_c{i}")
        m.d.comb += ci.eq(G[i - 1] | (P[i - 1] & cin))
        c[i] = ci
    m.d.comb += [
        s.eq(Cat(*[p[i] ^ c[i] for i in range(w)])),
        cout.eq(c[w]),
    ]
    return s, cout
