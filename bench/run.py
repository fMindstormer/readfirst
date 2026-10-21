"""Benchmark: for each book, words needed to read 25/50/75/90% of its sentences, per order, against
the proven minimum; also with the 1,000 most common words of the language already known."""

import json
import sys
import time
from pathlib import Path

import numpy as np

from readfirst.general import ranked_lemmas
from readfirst.order import Instance, by_frequency, by_list, curve, envelope, greedy, sidney
from readfirst.plan import plan
from readfirst.text import build

ROOT = Path(__file__).resolve().parent.parent
TITLES = {
    "en-alice": "Alice's Adventures in Wonderland", "en-bryant-stories": "Stories to Tell to Children",
    "en-father-brown": "The Innocence of Father Brown", "en-emma": "Emma", "en-metamorphosis": "Metamorphosis",
    "es-marianela": "Marianela", "es-don-quijote": "Don Quijote", "fr-candide": "Candide",
    "fr-tour-du-monde": "Le tour du monde en 80 jours", "fr-monte-cristo-1": "Le Comte de Monte-Cristo I",
    "de-die-verwandlung": "Die Verwandlung"}
TARGETS = (25, 50, 75, 90)


def needed(c, target):
    hit = (c >= target).nonzero()[0]
    return int(hit[0]) if len(hit) else None


def sample(c, env, limit, points=300):
    ks = sorted(set(np.linspace(0, limit, points).astype(int).tolist()) | {k for k, _ in env.corners if k <= limit})
    return ks


def run(name, know_top):
    lang = name[:2]
    book = build((ROOT / "books" / f"{name}.txt").read_text(), lang)
    general = ranked_lemmas(lang, list(book.token_count))
    known = {k for k in general[:know_top] if not k.startswith("\0")} if know_top else set()
    inst = Instance.from_book(book, known)
    t = time.time(); env = envelope(inst); t_env = time.time() - t
    W = inst.total
    orders = {"plan": sidney(inst, book.token_count, env), "greedy": greedy(inst, book.token_count),
              "book_freq": by_frequency(inst, book.token_count),
              "general_list": by_list(inst, [k for k in general if k not in known], book.token_count)}
    curves = {k: curve(inst, o) for k, o in orders.items()}
    res = {"book": name, "title": TITLES[name], "lang": lang, "know_top": know_top, "sentences": W,
           "words": len(inst.words), "known": len(known), "blocks": len(env.blocks), "envelope_seconds": round(t_env, 2),
           "needed": {"proof": [env.words_needed(W * p / 100) for p in TARGETS]},
           "first_step_reads": {}}
    for k, c in curves.items():
        res["needed"][k] = [needed(c, W * p / 100) for p in TARGETS]
        o = [w for w in orders[k] if w >= 0]
        steps = np.diff(curve(inst, o))
        res["first_step_reads"][k] = round(float((steps > 0).mean()), 3)   # share of words that complete a sentence
    limit = min(len(inst.words), max(res["needed"]["book_freq"][3] or 0, env.words_needed(W * 0.9)) + 200)
    ks = sample(curves["plan"], env, limit)
    res["curve"] = {"k": ks, "bound": [round(env.bound(k) / W, 5) for k in ks],
                    **{n: [round(int(curves[n][min(k, len(curves[n]) - 1)]) / W, 5) for k in ks] for n in curves}}
    res["plan"] = [{kk: (round(v, 4) if isinstance(v, float) else v) for kk, v in r.items()}
                   for r in plan(book, inst, orders["plan"], limit=120)]
    return res


if __name__ == "__main__":
    names = sys.argv[1:] or list(TITLES)
    out = []
    for name in names:
        for know in (0, 1000):
            r = run(name, know)
            out.append(r)
            n = r["needed"]
            print(f"{name:20s} know={know:4d} words={r['words']:5d} sents={r['sentences']:6d} blocks={r['blocks']:4d} "
                  f"env={r['envelope_seconds']:5.2f}s | 50%: proof {n['proof'][1]} plan {n['plan'][1]} greedy {n['greedy'][1]} "
                  f"freq {n['book_freq'][1]} list {n['general_list'][1]} | 90%: proof {n['proof'][3]} plan {n['plan'][3]} freq {n['book_freq'][3]}",
                  flush=True)
    (ROOT / "bench" / "results.json").write_text(json.dumps(out, ensure_ascii=False))
