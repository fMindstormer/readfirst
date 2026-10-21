"""The study pack: a self-contained reader page, an Anki deck and a plain plan table."""

from __future__ import annotations

import csv
import html
import json
import re
from collections import Counter
from pathlib import Path

from .course import Course, rent_or_buy, story_units, words_of
from .dictionary import SOURCES, gloss, wiktionary

TEMPLATE = Path(__file__).with_name("reader_template.html")


def short_gloss(g: str, limit: int = 24) -> str:
    """The first sense, short enough to sit under a word."""
    first = re.split(r";\s|,\s", g)[0].strip() if g else ""
    first = re.sub(r"\s*\((der|die|das)\)$", "", first)
    return first if len(first) <= limit else first[: limit - 1].rstrip() + "…"


def mark(text: str, spans, word_ids) -> str:
    """The sentence with the tokens of the given word ids wrapped in <b>."""
    out, at = [], 0
    for a, b, wid in sorted(spans):
        if wid in word_ids:
            out.append(html.escape(text[at:a])); out.append("<b>" + html.escape(text[a:b]) + "</b>"); at = b
    out.append(html.escape(text[at:]))
    return "".join(out)


def pack_data(title: str, doc, course: Course, tradeoff=None) -> dict:
    lang = doc.lang
    forms: dict[str, Counter] = {}
    for p in doc.paragraphs[doc.start:]:
        for ds in p.sentences:
            for t in ds.tokens:
                if t.key is not None:
                    forms.setdefault(t.key, Counter())[t.text] += 1
    ids: dict[str, int] = {}
    words = []

    def wid(w):
        if w not in ids:
            f = forms.get(w, Counter()).most_common(3)
            g = gloss(lang, w, [x for x, _ in f])
            ids[w] = len(words)
            words.append([w, f[0][0] if f else w, g, short_gloss(g)])
        return ids[w]

    known = set(course.known)
    learned_before = set(known)
    sessions = []
    for s in course.sessions:
        new = set(s.learn)
        paras, sent_list = [], []
        for i in s.paragraphs:
            ps = []
            for ds in doc.paragraphs[i].sentences:
                spans = []
                for t in ds.tokens:
                    if t.key is None:
                        continue
                    ws = (t.key,) + t.extra
                    if any(w in new for w in ws):
                        spans.append([t.start, t.end, 1, wid(next(w for w in ws if w in new))])
                    elif any(w not in course.learned and w not in known for w in ws):
                        spans.append([t.start, t.end, 2, wid(next(w for w in ws if w not in course.learned and w not in known))])
                ps.append([ds.text, spans])
                sent_list.append((ds, set(w for w in words_of(ds) if w not in known)))
            paras.append(ps)
        # each word's example: the sentence that becomes readable when it is learned, else the
        # shortest sentence of the session that uses it
        have = set(learned_before)
        gl = set(s.glossed)
        learn = []
        for w in s.learn:
            before = [d for d, u in sent_list if w in u and not (u - have - gl - {w})]
            have.add(w)
            if before:
                ds = min(before, key=lambda d: len(d.text)); left = 0
            else:
                cands = [(d, u) for d, u in sent_list if w in u]
                ds, u = min(cands, key=lambda c: (len(c[1] - have - gl), len(c[0].text)))
                left = len(u - have - gl)
            spans = [(t.start, t.end, w) for t in ds.tokens if t.key is not None and w in (t.key,) + t.extra]
            learn.append([wid(w), mark(ds.text, spans, {w}), left])
        learned_before |= new
        sessions.append({"title": s.title, "learn": learn, "paras": paras, "tokens": s.tokens,
                         "glosses": sum(s.glossed.values())})
    return {"title": title, "lang": lang, "source": SOURCES.get(lang, ""),
            "settings": {"cap": course.cap, "daily": course.daily, "known": len(known), "learn_cost": course.learn_cost},
            "stats": course.stats(), "tradeoff": tradeoff or [], "words": words, "sessions": sessions,
            "wiktionary": wiktionary(lang, "WORD")}


def write_reader(data: dict, path: Path, standalone: bool = True):
    """standalone: a complete HTML file that opens anywhere, offline. Otherwise the bare page,
    for hosts that add their own <head>."""
    page = TEMPLATE.read_text(encoding="utf-8")
    if standalone:
        page = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" '
                'content="width=device-width, initial-scale=1, viewport-fit=cover"></head><body>' + page + "</body></html>")
    page = page.replace("__TITLE__", html.escape(data["title"]))
    page = page.replace("/*DATA*/null", json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))
    path.write_text(page, encoding="utf-8")


def write_deck(data: dict, path: Path):
    """One note per word to learn, in study order (new cards are introduced in that order)."""
    import genanki
    model = genanki.Model(
        1607392319, "Readfirst word",
        fields=[{"name": "Word"}, {"name": "Form"}, {"name": "Meaning"}, {"name": "Example"}, {"name": "Session"}],
        templates=[{"name": "Read it", "qfmt": '<div class="ex">{{Example}}</div><div class="q">{{Form}}</div>',
                    "afmt": '{{FrontSide}}<hr id="answer"><div class="w">{{Word}}</div><div class="m">{{Meaning}}</div>'
                            '<div class="s">{{Session}}</div>'}],
        css=".card{font-family:Georgia,serif;font-size:22px;text-align:center;color:#1a2130;background:#fff}"
            ".ex{font-size:20px;line-height:1.5}.ex b{background:#ffe27a;padding:0 2px}.q{margin-top:14px;font-weight:bold}"
            ".w{font-weight:bold}.m{margin-top:8px}.s{margin-top:12px;font-size:13px;color:#737d90}")
    deck = genanki.Deck(abs(hash(data["title"])) % (1 << 31), f"Readfirst: {data['title']}")
    n = 0
    for k, s in enumerate(data["sessions"]):
        for wid, ex, _ in s["learn"]:
            w, form, g, _ = data["words"][wid]
            n += 1
            deck.add_note(genanki.Note(model=model, fields=[html.escape(w), html.escape(form), html.escape(g or "—"), ex,
                                                            f"Session {k + 1}: {html.escape(s['title'])}"],
                                       tags=[f"session_{k + 1:03d}"], due=n, guid=genanki.guid_for(data["title"], w)))
    genanki.Package(deck).write_to_file(str(path))
    return n


def write_table(data: dict, path: Path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["session", "word", "as written", "meaning", "example"])
        for k, s in enumerate(data["sessions"]):
            for wid, ex, _ in s["learn"]:
                word, form, g, _ = data["words"][wid]
                w.writerow([k + 1, word, form, g, re.sub(r"</?b>", "", html.unescape(ex))])


def tradeoff(doc, known, learn_cost=6, daily=15):
    """Words to learn against glosses per page, for each comfort level."""
    units, occ = story_units(doc, set(known))
    tok = sum(len(s.tokens) for p in doc.paragraphs[doc.start:] for s in p.sentences)
    out = []
    for cap in (1, 2, 3):
        learned, _ = rent_or_buy(units, occ, learn_cost, cap)
        g = sum(n for w, n in occ.items() if w not in learned)
        out.append({"cap": cap, "taught": len(learned), "glosses_per_page": round(250 * g / tok, 1),
                    "coverage": round(1 - g / tok, 3)})
    return out
