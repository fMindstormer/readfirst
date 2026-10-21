"""The bound and the orders, checked against brute force on small random books."""

import itertools
import random

import pytest

from readfirst.order import Instance, by_frequency, cost, curve, envelope, greedy, sidney


def random_instance(rng, n_words, n_sents, max_len=4, dup=True):
    sets = []
    for _ in range(n_sents):
        k = rng.randint(1, max_len)
        sets.append(frozenset(rng.sample(range(n_words), min(k, n_words))))
    if dup and sets and rng.random() < 0.5:
        sets.append(sets[0])                         # a repeated sentence
    if rng.random() < 0.2:
        sets.append(frozenset())                     # readable from the start
    return Instance.from_sets(sets)


def best_coverage(inst):
    """g(k): the most weight any k words make readable, by trying every set."""
    n = len(inst.words)
    g = [inst.base] * (n + 1)
    for mask in range(1 << n):
        k = bin(mask).count("1")
        v = inst.base + sum(int(w) for e, w in zip(inst.edges, inst.weights) if all(mask >> x & 1 for x in e))
        g[k] = max(g[k], v)
    return g


def best_cost(inst):
    return min(cost(inst, list(p)) for p in itertools.permutations(range(len(inst.words))))


SEEDS = range(300)


@pytest.mark.parametrize("seed", SEEDS)
def test_envelope_is_the_concave_hull_of_best_coverage(seed):
    rng = random.Random(seed)
    inst = random_instance(rng, rng.randint(1, 11), rng.randint(1, 14))
    env = envelope(inst)
    g = best_coverage(inst)
    for k in range(len(g)):
        assert g[k] <= env.bound(k) + 1e-9                       # an upper bound everywhere
    for k, gk in env.corners:
        assert g[k] == gk                                         # tight at every corner
    # concave: densities never increase
    assert all(a >= b for a, b in zip(env.density, env.density[1:]))
    # and it is the hull: every corner lies strictly above the chord of its neighbours
    for (k0, g0), (k1, g1), (k2, g2) in zip(env.corners, env.corners[1:], env.corners[2:]):
        assert (g1 - g0) * (k2 - k1) > (g2 - g1) * (k1 - k0)


@pytest.mark.parametrize("seed", SEEDS)
def test_block_order_meets_every_corner(seed):
    rng = random.Random(seed)
    inst = random_instance(rng, rng.randint(1, 12), rng.randint(1, 16))
    env = envelope(inst)
    order = sidney(inst, env=env)
    assert sorted(order) == list(range(len(inst.words)))
    c = curve(inst, order)
    for k, gk in env.corners:
        assert c[k] == gk


@pytest.mark.parametrize("seed", range(150))
def test_block_order_within_twice_optimal(seed):
    rng = random.Random(seed)
    inst = random_instance(rng, rng.randint(1, 7), rng.randint(1, 10))
    opt = best_cost(inst)
    s = cost(inst, sidney(inst))
    assert opt <= s <= 2 * opt


@pytest.mark.parametrize("seed", range(100))
def test_words_needed_is_a_lower_bound_and_tight_at_corners(seed):
    rng = random.Random(seed)
    inst = random_instance(rng, rng.randint(1, 10), rng.randint(1, 12))
    env = envelope(inst)
    g = best_coverage(inst)
    for target in range(inst.base, inst.total + 1):
        need = env.words_needed(target)
        true_need = min(k for k in range(len(g)) if g[k] >= target)
        assert need <= true_need
        assert env.bound(need) >= target - 1e-9 and (need == 0 or env.bound(need - 1) < target)
    for k, gk in env.corners:
        assert env.words_needed(gk) <= k


def test_curve_matches_naive_count():
    rng = random.Random(7)
    for _ in range(50):
        inst = random_instance(rng, 8, 10)
        order = list(range(len(inst.words))); rng.shuffle(order)
        c = curve(inst, order)
        for k in range(len(order) + 1):
            learned = set(order[:k])
            assert c[k] == inst.base + sum(int(w) for e, w in zip(inst.edges, inst.weights) if set(e) <= learned)


def test_greedy_respects_blocks():
    rng = random.Random(3)
    inst = random_instance(rng, 12, 15)
    env = envelope(inst)
    order = greedy(inst, blocks=env.blocks)
    pos = {w: i for i, w in enumerate(order)}
    for a, b in zip(env.blocks, env.blocks[1:]):
        assert max(pos[w] for w in a) < min(pos[w] for w in b)


def test_tauber_example():
    """James Tauber's example: frequency order reads 2 sentences after 4 words; moving h ahead of
    d reads 3."""
    sents = ["a b", "b a", "h a b", "d a b e c", "d a g f"]
    inst = Instance.from_sets([frozenset(s.split()) for s in sents])
    env = envelope(inst)
    assert env.bound(4) >= 3
    c = curve(inst, sidney(inst))
    assert c[3] == 3 and c[4] >= 3
