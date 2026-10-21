"""python -m readfirst course BOOK.txt --lang es [--comfort balanced] [--know-top 1000] --out pack/
python -m readfirst BOOK.txt --lang es [--know-top 1000] [--known words.txt] [--plan plan.tsv]"""

import argparse
import csv
import sys
from pathlib import Path

from .general import ranked_lemmas
from .order import Instance, by_frequency, by_list, curve, envelope, sidney
from .plan import plan
from .text import build


def needed(c, target):
    hit = (c >= target).nonzero()[0]
    return int(hit[0]) if len(hit) else None


def known_words(a, lang, lemmas, general):
    known = set()
    if a.know_top:
        known |= {k for k in general[: a.know_top] if not k.startswith("\0")}
    if a.known:
        import simplemma
        for line in Path(a.known).read_text(encoding="utf-8").split():
            known |= {line, line.lower(), simplemma.lemmatize(line, lang=lang).lower()}
        known &= set(lemmas) | known
    return known


def course_main(argv):
    from collections import Counter
    from .course import COMFORT, build_course
    from .pack import pack_data, tradeoff, write_deck, write_reader, write_table
    from .text import analyze
    ap = argparse.ArgumentParser(prog="readfirst course", description="Turn a book into a course: study a few words, read a few pages, repeat.")
    ap.add_argument("book")
    ap.add_argument("--lang", required=True, help="en, es, fr or de (others work without meanings)")
    ap.add_argument("--title", help="book title for the pack (default: the file name)")
    ap.add_argument("--comfort", choices=list(COMFORT), default="balanced",
                    help="at most 1, 2 or 3 glossed words per sentence (default balanced: 2)")
    ap.add_argument("--daily", type=int, default=15, help="new words a day (default 15)")
    ap.add_argument("--learn-cost", type=float, default=6, help="how many look-ups one flashcard is worth (default 6)")
    ap.add_argument("--known", help="file of words you already know")
    ap.add_argument("--know-top", type=int, default=0, help="assume you know the N most common words of the language")
    ap.add_argument("--out", default="pack", help="folder for reader.html, deck.apkg and words.tsv")
    a = ap.parse_args(argv)
    text = Path(a.book).read_text(encoding="utf-8", errors="replace")
    doc, _ = analyze(text, a.lang)
    lemmas = Counter(t.key for p in doc.paragraphs for d in p.sentences for t in d.tokens if t.key)
    known = known_words(a, a.lang, list(lemmas), ranked_lemmas(a.lang, list(lemmas)) if a.know_top else [])
    course = build_course(doc, known, cap=COMFORT[a.comfort], learn_cost=a.learn_cost, daily=a.daily)
    title = a.title or Path(a.book).stem
    data = pack_data(title, doc, course, tradeoff(doc, known, a.learn_cost, a.daily))
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    write_reader(data, out / "reader.html")
    n = write_deck(data, out / "deck.apkg")
    write_table(data, out / "words.tsv")
    st = course.stats()
    print(f"{title}: {st['sessions']} sessions; learn {st['taught']:,} words ({a.daily} a day), gloss the rest "
          f"({st['glosses_per_page']} a page, {st['coverage']:.1%} of the text known while reading).")
    print(f"First page on day {st['start_day']}, last page on day about {st['days']:,}." + ("" if st["optimal"] else " (choice not proven optimal)"))
    print("comfort      words to learn   glosses a page")
    for t in data["tradeoff"]:
        print(f"  {list(COMFORT)[t['cap'] - 1]:12s} {t['taught']:>10,}   {t['glosses_per_page']:>10}")
    print(f"wrote {out / 'reader.html'}, {out / 'deck.apkg'} ({n} cards), {out / 'words.tsv'}")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "course":
        return course_main(argv[1:])
    ap = argparse.ArgumentParser(prog="readfirst", description="Which words to learn first to read a book soonest.")
    ap.add_argument("book")
    ap.add_argument("--lang", help="language code (en, es, fr, de, ...); guessed if omitted")
    ap.add_argument("--known", help="file of words you already know, one per line (any form)")
    ap.add_argument("--know-top", type=int, default=0, help="assume you know the N most common words of the language")
    ap.add_argument("--plan", help="write the study plan here (tab-separated, importable into Anki)")
    ap.add_argument("--show", type=int, default=15, help="plan rows to print")
    a = ap.parse_args(argv)

    text = Path(a.book).read_text(encoding="utf-8", errors="replace")
    lang = a.lang
    if not lang:
        from simplemma import langdetect
        lang = langdetect(text[:20000], lang=("en", "es", "fr", "de", "it", "pt", "nl"))[0][0]
    book = build(text, lang)
    lemmas = list(book.token_count)
    general = ranked_lemmas(lang, lemmas)
    known = known_words(a, lang, lemmas, general)
    inst = Instance.from_book(book, known)
    env = envelope(inst)
    W = inst.total
    orders = {"this plan": sidney(inst, book.token_count, env),
              "book frequency order": by_frequency(inst, book.token_count)}
    curves = {k: curve(inst, o) for k, o in orders.items()}
    print(f"{Path(a.book).name}: {W:,} sentences of 3+ words, {len(inst.words):,} words to learn"
          + (f" ({len(known & set(lemmas)):,} already known)" if known else "") + ".")
    print(f"{'words needed to read':26s}" + "".join(f"{p:>8d}%" for p in (25, 50, 75, 90)))
    print(f"  {'fewest possible (proof)':24s}" + "".join(f"{env.words_needed(W * p / 100):>9,}" for p in (25, 50, 75, 90)))
    for name, c in curves.items():
        print(f"  {name:24s}" + "".join(f"{(needed(c, W * p / 100) or 0):>9,}" for p in (25, 50, 75, 90)))
    rows = plan(book, inst, orders["this plan"])
    if a.plan:
        with open(a.plan, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter="\t")
            w.writerow(["step", "word", "as written", "uses", "example", "readable after"])
            for r in rows:
                w.writerow([r["step"], r["lemma"], r["form"], r["uses"], r["example"].replace("**", ""), f"{r['readable']:.1%}"])
        print(f"plan: {a.plan}")
    for r in rows[: a.show]:
        print(f"  {r['step']:4d}  {r['lemma']:14s} {r['readable']:6.1%}  {r['example'][:80]}")


if __name__ == "__main__":
    sys.exit(main())
