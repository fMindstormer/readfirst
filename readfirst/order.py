"""Orders in which to learn a book's words, and the best any order could do.

Each sentence is readable once every word in it is known. Learning one word per step, we want
sentences to become readable as early as possible: maximise the area under the curve "sentences
readable after k words". Writing C_s for the step at which sentence s's last word is learned, that
is minimising sum_s w_s C_s: single-machine scheduling with precedence constraints,
1 | prec | sum w_j C_j. Words are unit-length jobs of weight 0; a sentence is a zero-length job of
weight w_s that must follow all of its words.

Sidney (1975) showed optimal schedules respect a decomposition into blocks: repeatedly take the
initial set with the highest ratio of weight to length, here the set of words that completes the
most sentences per word. That set is a densest sub-hypergraph, a maximum-weight closure, which a
single max-flow finds exactly (Picard 1976; Goldberg 1984). Any order that respects the blocks is
within a factor 2 of optimal (Chekuri & Motwani 1999; Margot, Queyranne & Wang 2003).

The same computation gives a certificate. Let g(k) be the most sentences any k words can make
readable. The block boundaries are exactly the corners of the upper concave envelope of g, so no
order can be above the envelope at any k, and the block order meets it at every corner.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from heapq import heappop, heappush
from math import gcd

import numpy as np
from ortools.graph.python import max_flow


@dataclass
class Instance:
    words: list[str]                  # index -> lemma
    edges: list[tuple[int, ...]]      # sentence -> indices of the words it needs
    weights: np.ndarray               # sentence weights (merged duplicates count several times)
    base: int = 0                     # weight readable before learning anything

    @property
    def total(self) -> int:
        return self.base + int(self.weights.sum())

    @classmethod
    def from_book(cls, book, known=()) -> "Instance":
        known = set(known)
        words = sorted({w for s in book.sentences for w in s.words} - known,
                       key=lambda w: (-book.token_count[w], w))
        index = {w: i for i, w in enumerate(words)}
        edges, weights, base = [], [], 0
        for s in book.sentences:
            e = tuple(sorted(index[w] for w in s.words if w not in known))
            if e:
                edges.append(e); weights.append(s.count)
            else:
                base += s.count
        return cls(words, edges, np.array(weights, dtype=np.int64), base)

    @classmethod
    def from_sets(cls, sets, weights=None) -> "Instance":
        words = sorted({w for s in sets for w in s})
        index = {w: i for i, w in enumerate(words)}
        edges = [tuple(sorted(index[w] for w in s)) for s in sets]
        base = sum(1 for e in edges if not e) if weights is None else 0
        keep = [i for i, e in enumerate(edges) if e]
        w = np.ones(len(keep), dtype=np.int64) if weights is None else np.array([weights[i] for i in keep])
        return cls([str(x) for x in words], [edges[i] for i in keep], w, base)


# ----------------------------------------------------------------------------------------- curves

def completion(inst: Instance, order) -> np.ndarray:
    """Step (1-based) at which each sentence becomes readable; len(order) + 1 if never.
    Entries of -1 in the order are steps spent on words the book does not use."""
    n = len(order)
    pos = np.full(len(inst.words), n + 1, dtype=np.int64)
    for k, w in enumerate(order):
        if w >= 0 and pos[w] > n:
            pos[w] = k + 1
    return np.array([pos[list(e)].max() for e in inst.edges], dtype=np.int64)


def curve(inst: Instance, order) -> np.ndarray:
    """c[k] = weight readable after the first k steps of the order, k = 0..len(order)."""
    n = len(order)
    c = np.zeros(n + 2, dtype=np.int64)
    np.add.at(c, completion(inst, order), inst.weights)
    return inst.base + np.cumsum(c)[: n + 1]


def cost(inst: Instance, order) -> int:
    """sum_s w_s C_s, the scheduling objective (smaller is better)."""
    return int((completion(inst, order) * inst.weights).sum())


# ------------------------------------------------------------------------------- simple orders

def by_frequency(inst: Instance, counts) -> list[int]:
    return sorted(range(len(inst.words)), key=lambda i: (-counts[inst.words[i]], inst.words[i]))


def by_list(inst: Instance, ranked, counts) -> list[int]:
    """Follow a general frequency list; list words the book never uses still cost a step (-1).
    Book words missing from the list come last, by frequency in the book."""
    index = {w: i for i, w in enumerate(inst.words)}
    out, seen = [], set()
    for w in ranked:
        if w in seen:
            continue
        seen.add(w)
        out.append(index.get(w, -1))
    while out and out[-1] == -1:
        out.pop()
    rest = [i for i in by_frequency(inst, counts) if inst.words[i] not in seen]
    return out + rest


def greedy(inst: Instance, counts=None, blocks=None, credit=(0.0, 1.0, 0.05, 0.002)) -> list[int]:
    """Learn the word that makes the most sentences readable now, with a little credit for
    sentences it brings to one or two missing words; ties go to the more frequent word.
    With blocks, words are only chosen from the current block until it is exhausted."""
    n = len(inst.words)
    freq = [counts[w] for w in inst.words] if counts else [0] * n
    of_word = [[] for _ in range(n)]
    for j, e in enumerate(inst.edges):
        for w in e:
            of_word[w].append(j)
    miss = [len(e) for e in inst.edges]
    wt = inst.weights.tolist()
    f = lambda m: credit[m] if m < len(credit) else 0.0
    score = [0.0] * n
    for j, e in enumerate(inst.edges):
        v = f(len(e)) * wt[j]
        if v:
            for w in e:
                score[w] += v
    if blocks is None:
        blocks = [list(range(n))]
    known = [False] * n
    order = []
    for block in blocks:
        current = set(block)
        heap = [(-score[w], -freq[w], w) for w in block]
        heap.sort()
        while current:
            s, _, w = heappop(heap)
            if known[w] or -s != score[w]:
                continue
            known[w] = True; current.discard(w); order.append(w)
            for j in of_word[w]:
                old = miss[j]; miss[j] -= 1
                d = (f(miss[j]) - f(old)) * wt[j]
                if d:
                    for u in inst.edges[j]:
                        if not known[u]:
                            score[u] += d
                            if u in current:
                                heappush(heap, (-score[u], -freq[u], u))
    return order


# ------------------------------------------------------------------- densest blocks, envelope

@dataclass
class Envelope:
    blocks: list[list[int]]           # Sidney blocks, densest first
    density: list[Fraction]           # sentences completed per word, block by block
    corners: list[tuple[int, int]]    # (k, g(k)) at block boundaries, from (0, base)

    def bound(self, k: float) -> float:
        """No order can make more than this weight readable with k words."""
        for (k0, g0), (k1, g1) in zip(self.corners, self.corners[1:]):
            if k <= k1:
                return g0 + (g1 - g0) * (k - k0) / (k1 - k0)
        return self.corners[-1][1]

    def words_needed(self, target: float) -> int:
        """Fewest words any order needs before `target` weight is readable."""
        for (k0, g0), (k1, g1) in zip(self.corners, self.corners[1:]):
            if target <= g1:
                if target <= g0:
                    return k0
                # smallest integer k with g0 + (g1-g0)(k-k0)/(k1-k0) >= target
                num = (target - g0) * (k1 - k0)
                return k0 + int(-(-Fraction(num) // (g1 - g0)))
        raise ValueError("target above the total")


def _max_closure(edges, weights, verts, p, q):
    """Maximise q * w(edges inside S) - p * |S| over S within verts (edges given as tuples of
    vertices in verts). Returns (value, minimal optimal S)."""
    vid = {v: i for i, v in enumerate(verts)}
    m = len(edges)
    src, snk = m + len(verts), m + len(verts) + 1
    total = q * int(sum(weights))
    tails, heads, caps = [], [], []
    for j, (e, w) in enumerate(zip(edges, weights)):
        tails.append(src); heads.append(j); caps.append(q * int(w))
        for v in e:
            tails.append(j); heads.append(m + vid[v]); caps.append(total + 1)
    for i in range(len(verts)):
        tails.append(m + i); heads.append(snk); caps.append(p)
    smf = max_flow.SimpleMaxFlow()
    smf.add_arcs_with_capacity(np.array(tails, dtype=np.int32), np.array(heads, dtype=np.int32),
                               np.array(caps, dtype=np.int64))
    status = smf.solve(src, snk)
    assert status == smf.OPTIMAL, status
    value = total - smf.optimal_flow()
    side = smf.get_source_side_min_cut()
    S = [verts[i - m] for i in side if m <= i < m + len(verts)]
    return value, S


def envelope(inst: Instance) -> Envelope:
    """Sidney decomposition by recursive parametric max-closure.

    Keep a nested pair A within B of corner sets. With lambda = (g(B) - g(A)) / (|B| - |A|), both
    have the same value g - lambda |S|; a max-closure between them either finds a set C with a
    higher value (a corner in between: recurse on A..C and C..B) or proves A and B adjacent.
    Each sentence and each word belongs to exactly one sub-problem per level."""
    n = len(inst.words)
    blocks, dens = [], []
    # sub-problem: (vertices of B minus A, sentences inside B but not inside A, as parts outside A)
    stack = [(list(range(n)), list(range(len(inst.edges))), [tuple(e) for e in inst.edges])]
    while stack:
        verts, eids, parts = stack.pop()
        W = int(inst.weights[eids].sum()) if eids else 0
        if not verts:
            continue
        g = gcd(W, len(verts)) or 1
        p, q = W // g, len(verts) // g
        value, S = (0, []) if W == 0 else _max_closure(parts, inst.weights[eids].tolist(), verts, p, q)
        if value <= 0:
            blocks.append(verts); dens.append(Fraction(W, len(verts)))
            continue
        inS = set(S)
        left = [(j, e) for j, e in zip(eids, parts) if all(v in inS for v in e)]
        right = [(j, tuple(v for v in e if v not in inS)) for j, e in zip(eids, parts) if not all(v in inS for v in e)]
        rest = [v for v in verts if v not in inS]
        stack.append((rest, [j for j, _ in right], [e for _, e in right]))      # processed second
        stack.append((S, [j for j, _ in left], [e for _, e in left]))           # densest first
    corners, k, gk = [(0, inst.base)], 0, inst.base
    for b, d in zip(blocks, dens):
        k += len(b); gk += int(d * len(b))
        corners.append((k, gk))
    return Envelope(blocks, dens, corners)


def sidney(inst: Instance, counts=None, env: Envelope | None = None) -> list[int]:
    """Learn the densest block first; inside a block, the greedy order."""
    env = env or envelope(inst)
    return greedy(inst, counts, blocks=env.blocks)
