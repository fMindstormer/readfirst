"""A general frequency list (from the wordfreq package) mapped onto a book's lemmas."""

from __future__ import annotations

from collections import defaultdict

import simplemma

from .text import KEEP


def ranked_lemmas(lang: str, book_lemmas, n: int = 50000) -> list[str]:
    """The book's lemmas in the order a general frequency list reaches them; list words the book
    never uses are kept as placeholders so they still cost a step."""
    from wordfreq import top_n_list
    lower = defaultdict(list)
    for k in book_lemmas:
        lower[k.lower()].append(k)
    out, seen = [], set()
    for w in top_n_list(lang, n):
        if w in KEEP.get(lang, ()):
            cands = [w]
        else:
            cands = [simplemma.lemmatize(w, lang=lang).lower(), w]
            if lang == "de":
                cands.insert(0, simplemma.lemmatize(w.capitalize(), lang=lang).lower())
        keys = next((lower[c] for c in cands if c in lower), None)
        if keys is None:
            key = "\0" + cands[0]                      # not in the book: a wasted step
            keys = [key]
        for k in keys:
            if k not in seen:
                seen.add(k); out.append(k)
    return out
