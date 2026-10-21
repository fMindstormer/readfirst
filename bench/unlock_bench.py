"""While studying a session's list, how much of the coming pages is readable already: the unlock
order against the same list studied most-frequent-first (balanced comfort, from zero)."""
import sys
from collections import Counter
from pathlib import Path

from readfirst.course import build_course, story_units, words_of
from readfirst.text import analyze

ROOT = Path(__file__).resolve().parent.parent
for name in sys.argv[1:] or ["en-alice", "es-marianela", "fr-tour-du-monde", "de-die-verwandlung"]:
    doc, _ = analyze((ROOT / "books" / f"{name}.txt").read_text(), name[:2])
    c = build_course(doc, cap=2)
    _, occ = story_units(doc, set())
    num = {"unlock": 0.0, "frequency": 0.0}
    steps = 0
    have = set()
    for s in c.sessions:
        sents = [set(words_of(d)) for i in s.paragraphs for d in doc.paragraphs[i].sentences]
        free = set(s.glossed)
        for label, order in (("unlock", s.learn), ("frequency", sorted(s.learn, key=lambda w: (-occ[w], w)))):
            k = set(have)
            for w in order:
                k.add(w)
                num[label] += sum(1 for u in sents if not (u - k - free)) / max(1, len(sents))
        steps += len(s.learn)
        have |= set(s.learn)
    print(f"{name:20s} readable share of the coming pages while studying: unlock order {num['unlock'] / steps:.1%}, "
          f"most-frequent-first {num['frequency'] / steps:.1%}")
