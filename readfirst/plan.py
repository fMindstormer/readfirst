"""A study plan: each word in order, with a sentence that becomes readable when it is learned."""

from __future__ import annotations

import re

from .order import Instance, completion


def highlight(sentence, word, mark="**"):
    """Mark the tokens of `sentence` whose lemma is `word`."""
    toks = [t for t, k in sentence.pairs if k == word]
    text = sentence.text
    for t in sorted(set(toks), key=len, reverse=True):
        text = re.sub(rf"(?<![^\W\d_]){re.escape(t)}(?![^\W\d_])", f"{mark}{t}{mark}", text)
    return text


def plan(book, inst: Instance, order, limit=None):
    """Rows: step, lemma, written form, uses in the book, example, readable share after the step.
    The example is the shortest sentence (of 4+ tokens if possible) that this word completes; if
    it completes none, the sentence containing it with the fewest words still unknown."""
    in_inst = set(inst.words)
    first = {}
    for s in book.sentences:                         # sentences that reduce to the same unknown words
        first.setdefault(frozenset(w for w in s.words if w in in_inst), s)
    edge_sent = [first[frozenset(inst.words[i] for i in e)] for e in inst.edges]
    done = completion(inst, order)
    of_word = [[] for _ in inst.words]
    for j, e in enumerate(inst.edges):
        for w in e:
            of_word[w].append(j)
    pos = {w: k + 1 for k, w in enumerate(order) if w >= 0}
    readable = inst.base
    rows = []
    for k, w in enumerate(order[:limit] if limit else order, start=1):
        if w < 0:
            continue
        finished = [j for j in of_word[w] if done[j] == k]
        readable += int(sum(inst.weights[j] for j in finished))
        if finished:
            pick = min(finished, key=lambda j: (len(edge_sent[j].pairs) < 4, len(edge_sent[j].text)))
            missing = 0
        else:
            unknown = lambda j: sum(1 for v in inst.edges[j] if pos.get(v, 10 ** 9) > k)
            pick = min(of_word[w], key=lambda j: (unknown(j), len(edge_sent[j].text)))
            missing = unknown(pick)
        lemma = inst.words[w]
        rows.append({"step": k, "lemma": lemma, "form": book.surface.get(lemma, lemma),
                     "uses": book.token_count[lemma], "example": highlight(edge_sent[pick], lemma),
                     "unknown_in_example": missing, "readable": readable / inst.total})
    return rows
