"""The course on every book, from zero and knowing the 1,000 most common words: each comfort level,
the exact rent-or-buy choice against the obvious rule, and how often the book reviews what it
taught."""
import json
import sys
from collections import Counter
from pathlib import Path

from readfirst.course import build_course, rent_or_buy_rule, story_units
from readfirst.general import ranked_lemmas
from readfirst.text import analyze

ROOT = Path(__file__).resolve().parent.parent
BOOKS = ["en-alice", "en-bryant-stories", "en-father-brown", "en-emma", "en-metamorphosis", "es-marianela",
         "es-don-quijote", "fr-candide", "fr-tour-du-monde", "fr-monte-cristo-1", "de-die-verwandlung"]
L = 6


def run(name):
    doc, _ = analyze((ROOT / "books" / f"{name}.txt").read_text(), name[:2])
    lemmas = Counter(t.key for p in doc.paragraphs for d in p.sentences for t in d.tokens if t.key)
    general = ranked_lemmas(doc.lang, list(lemmas))
    rows = []
    for know in (0, 1000):
        known = {k for k in general[:know] if not k.startswith("\0")}
        units, occ = story_units(doc, known)
        for cap in (1, 2, 3):
            c = build_course(doc, known, cap=cap, learn_cost=L)
            st = c.stats()
            rule = rent_or_buy_rule(units, occ, L, cap)
            cost = lambda S: L * len(S) + sum(n for w, n in occ.items() if w not in S)
            # how often a taught word comes back after the session that teaches it
            where = {w: k for k, s in enumerate(c.sessions) for w in s.learn}
            later = Counter()
            for k, s in enumerate(c.sessions):
                for i in s.paragraphs:
                    for d in doc.paragraphs[i].sentences:
                        for t in d.tokens:
                            for w in ((t.key,) + t.extra if t.key else ()):
                                if w in where and where[w] < k:
                                    later[w] += 1
            st.update(book=name, know_top=know, cap=cap, words_in_story=len(occ),
                      met_again_3plus=round(sum(1 for w in where if later[w] >= 3) / max(1, len(where)), 3),
                      rule_taught=len(rule), cost=cost(c.learned), rule_cost=cost(rule))
            rows.append(st)
    return rows


if __name__ == "__main__":
    out = []
    for b in sys.argv[1:] or BOOKS:
        for r in run(b):
            out.append(r)
            print(f"{r['book']:20s} know={r['know_top']:4d} cap={r['cap']} learn {r['taught']:5d}/{r['words_in_story']:5d} "
                  f"glosses/page {r['glosses_per_page']:5.1f} coverage {r['coverage']:.1%} first page day {r['start_day']:3d} "
                  f"last day {r['days']:4d} met again 3+ {r['met_again_3plus']:.0%} | rule: learn {r['rule_taught']:5d} "
                  f"cost +{r['rule_cost'] / r['cost'] - 1:.1%}", flush=True)
    (ROOT / "bench" / "course_results.json").write_text(json.dumps(out))
