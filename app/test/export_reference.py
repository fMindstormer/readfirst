"""Reference outputs of the Python implementation, for checking the JavaScript port.

    python app/test/export_reference.py      -> app/test/ref-<book>.json

For each sample book: the analysed document (paragraphs, headings, sentences, tokens with spans,
dictionary forms and attached words, names, where the story starts), the general frequency ranking
of the book's words, and two courses (from zero, and knowing the 1,000 most common words) built
with the rule method the browser uses, with each session's study list and examples.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from readfirst.course import build_course, rent_or_buy_rule, story_units  # noqa: E402
from readfirst.general import ranked_lemmas  # noqa: E402
from readfirst.pack import pack_data  # noqa: E402
from readfirst.text import analyze  # noqa: E402

BOOKS = {"marianela": ("es", "es-marianela.txt"), "candide": ("fr", "fr-candide.txt"),
         "verwandlung": ("de", "de-die-verwandlung.txt"), "alice": ("en", "en-alice.txt")}


def main():
    out_dir = Path(__file__).resolve().parent
    for name, (lang, file) in BOOKS.items():
        text = (ROOT / "books" / file).read_text(encoding="utf-8")
        doc, _ = analyze(text, lang)
        lemmas = sorted({t.key for p in doc.paragraphs for d in p.sentences for t in d.tokens if t.key})
        ranked = ranked_lemmas(lang, lemmas)
        ref = {"lang": lang, "start": doc.start, "names": sorted(doc.names),
               "paragraphs": [{"heading": p.heading, "sentences": [
                   {"text": d.text, "tokens": [[t.text, t.start, t.end, t.key, list(t.extra)] for t in d.tokens]}
                   for d in p.sentences]} for p in doc.paragraphs],
               "ranked": ranked[:3000], "courses": {}}
        for label, known in (("zero", set()), ("top1000", {k for k in ranked[:1000] if not k.startswith("\0")})):
            course = build_course(doc, known, cap=2, learn_cost=6, daily=15, method="rule")
            data = pack_data(name, doc, course, tradeoff=None)
            trade = []
            units, occ = story_units(doc, known)
            tok = sum(len(s.tokens) for p in doc.paragraphs[doc.start:] for s in p.sentences)
            for cap in (1, 2, 3):
                learned = rent_or_buy_rule(units, occ, 6, cap)
                g = sum(n for w, n in occ.items() if w not in learned)
                trade.append({"cap": cap, "taught": len(learned), "glosses": g, "tokens": tok})
            ref["courses"][label] = {
                "known": sorted(known), "learned": sorted(course.learned), "stats": course.stats(), "tradeoff": trade,
                "sessions": [{"title": s.title, "paragraphs": [s.paragraphs.start, s.paragraphs.stop], "tokens": s.tokens,
                              "learn": s.learn, "glossed": dict(sorted(s.glossed.items())), "sentences": s.sentences,
                              "sentences_glossed": s.sentences_glossed} for s in course.sessions],
                "examples": [[[data["words"][wid][0], ex, left] for wid, ex, left in s["learn"]] for s in data["sessions"]],
                "words": data["words"],
            }
        path = out_dir / f"ref-{name}.json"
        path.write_text(json.dumps(ref, ensure_ascii=False), encoding="utf-8")
        st = ref["courses"]["zero"]["stats"]
        print(f"{name}: {sum(len(p['sentences']) for p in ref['paragraphs'])} sentences, start {doc.start}, "
              f"{len(lemmas)} words; course from zero: {st['sessions']} sessions, learn {st['taught']}")


if __name__ == "__main__":
    main()
