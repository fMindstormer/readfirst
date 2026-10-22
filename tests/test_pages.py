"""Introductions on pages: the flows match the best schedules found by trying every one, and the
gloss count is the additive objective the min-cost flow optimises."""

import itertools
import random

import pytest

from bench.pages_bench import evaluate, fewest_glosses, gains, most_comfortable, most_introductions, occurrences


def random_book(rng, n_pages=4, n_words=6):
    """Pages of sentences of one-word tokens; word ids 0..n_words-1, the first ones worth learning."""
    return [[[[rng.randrange(n_words)] for _ in range(rng.randint(1, 5))] for _ in range(rng.randint(1, 3))]
            for _ in range(n_pages)]


def schedules(R, K, npages):
    words = list(R)
    for choice in itertools.product(*[[None, *R[w]] for w in words]):
        at = {w: p for w, p in zip(words, choice) if p is not None}
        if all(sum(1 for p in at.values() if p == q) <= K for q in range(npages)):
            yield at


@pytest.mark.parametrize("seed", range(150))
def test_flows_are_exact(seed):
    rng = random.Random(seed)
    pages = random_book(rng)
    learned = {w for w in range(rng.randint(2, 5))}
    c = occurrences(pages)
    R = gains(c, learned & set(c))
    K = rng.randint(1, 2)
    every = list(schedules(R, K, len(pages)))
    gain = lambda at: sum(R[w][p] for w, p in at.items())
    assert most_introductions(R, K, len(pages)) == max(len(at) for at in every)
    at = fewest_glosses(R, K, len(pages))
    assert gain(at) == max(gain(s) for s in every)
    most = fewest_glosses(R, K, len(pages), bonus=1 + max((r for w in R for r in R[w].values()), default=0))
    assert len(most) == max(len(s) for s in every)
    assert gain(most) == max(gain(s) for s in every if len(s) == len(most))
    # with one-word tokens the glosses are every occurrence less those the schedule avoids
    tokens = sum(len(s) for page in pages for s in page)
    assert evaluate(pages, at)[0] == tokens - gain(at)
    assert all(sum(1 for p in at.values() if p == q) <= K for q in range(len(pages)))


@pytest.mark.parametrize("seed", range(40))
def test_comfort_is_exact(seed):
    rng = random.Random(1000 + seed)
    pages = random_book(rng)
    learned = {w for w in range(rng.randint(2, 5))}
    c = occurrences(pages)
    R = gains(c, learned & set(c))
    K = rng.randint(1, 2)
    every = list(schedules(R, K, len(pages)))
    at, bound = most_comfortable(pages, R, K, 10)
    best = min(evaluate(pages, s)[1] for s in every)
    assert evaluate(pages, at)[1] == best == bound
    assert evaluate(pages, at)[0] == min(evaluate(pages, s)[0] for s in every if evaluate(pages, s)[1] == best)
