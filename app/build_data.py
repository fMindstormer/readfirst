"""Export what the browser app needs, one JSON file per language: app/data/<lang>.json

    python app/build_data.py            (needs simplemma, wordfreq and the compiled dicts/)

  lemmas   written form -> dictionary form, for the forms a general word list knows (wordfreq's
           large list, top 150,000), as simplemma lemmatizes them; for French also the rarer
           inflected forms Wiktionary lists (passé simple, subjunctive), where simplemma agrees or
           does not know the form. Forms whose dictionary form is
           themselves are left out. Encoded per dictionary form: "lemma<TAB>f1|f2|...", where each
           form is one base-36 digit (how many leading characters it shares with the lemma) and
           the rest of the form.
  known    (Spanish) more forms simplemma knows, the ones the clitic split asks about.
  ruled    (Spanish) forms in `lemmas` that simplemma lemmatizes by rule, not from its dictionary:
           the clitic split treats them as unknown, as Python does.
  freq     the 30,000 most common written forms, most common first: the app maps them onto a
           book's words to estimate what a learner knows.
  gloss    short English meanings, for the forms and dictionary forms above.
"""

from __future__ import annotations

import gzip
import json
import re
import sys
from pathlib import Path

import simplemma
from simplemma.strategies.dictionaries import DefaultDictionaryFactory
from wordfreq import top_n_list

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from readfirst.dictionary import DICTS, OVERRIDES, SOURCES, load  # noqa: E402
from readfirst.text import CLITICS_ES, KEEP  # noqa: E402

OUT = Path(__file__).resolve().parent / "data"
N_FORMS = 150_000
N_FREQ = 30_000
LICENCES = {
    "lemmas": "Dictionary forms from simplemma 2.0 (MIT licence; its word lists are derived from "
              "lemmatization-lists by Michal Měchura, ODbL) applied to the wordfreq word list "
              "(Robyn Speer; data CC BY-SA 4.0).",
    "freq": "wordfreq (Robyn Speer), data CC BY-SA 4.0.",
}
VERB = re.compile(r"(ar|er|ir|ír|ando|iendo|yendo)$")


def b36(n):
    return "0123456789abcdefghijklmnopqrstuvwxyz"[min(n, 35)]


def encode(table: dict) -> str:
    by = {}
    for form, lemma in table.items():
        by.setdefault(lemma, []).append(form)
    lines = []
    for lemma in sorted(by):
        codes = []
        for f in sorted(by[lemma]):
            k = 0
            while k < min(len(f), len(lemma), 35) and f[k] == lemma[k]:
                k += 1
            codes.append(b36(k) + f[k:])
        lines.append(lemma + "\t" + "|".join(codes))
    return "\n".join(lines)


def build(lang: str) -> dict:
    forms = top_n_list(lang, N_FORMS, wordlist="large")
    table, identity = {}, set()

    def add(w):
        if not w or w in table or w in identity:
            return
        r = simplemma.lemmatize(w, lang=lang)
        if r != w:
            table[w] = r
        else:
            identity.add(w)

    for w in forms:
        add(w)
        if lang == "de":
            add(w.capitalize())
    extra = DICTS / f"{lang}-forms.json.gz"
    if extra.exists():                     # rarer forms from the dictionary (French: Wiktionary's inflections)
        listed = set(table) | identity
        for f, head in json.loads(gzip.open(extra, "rt", encoding="utf-8").read()).items():
            f, head = f.lower(), head.lower()
            if f not in listed and f != head and simplemma.lemmatize(f, lang=lang) in (f, head):
                table[f] = head
                listed.add(f)
    if lang == "de":                       # forms with ß (wordfreq writes them with ss)
        wordset = set(forms)
        for k in DefaultDictionaryFactory().get_dictionary("de"):
            if "ß" in k and k.lower().replace("ß", "ss") in wordset:
                add(k)
    out = {"lang": lang, "version": 1, "lemmas": encode(table)}
    if lang == "es":
        known = sorted(w for w in identity
                       if (w.endswith(CLITICS_ES) or VERB.search(w)) and simplemma.is_known(w, lang="es"))
        out["known"] = "\n".join(known)
        out["ruled"] = "\n".join(sorted(w for w in table if not simplemma.is_known(w, lang="es")))
    out["freq"] = "\n".join(top_n_list(lang, N_FREQ, wordlist="large"))
    # glosses for every dictionary form and written form the app can produce
    d = load(lang)
    keys = set(table.values()) | identity | set(KEEP.get(lang, ())) | set(OVERRIDES.get(lang, {}))
    keys |= {k.lower() for k in keys}
    keys |= {f for f, lemma in table.items() if lemma not in d and lemma.lower() not in d}   # a form's own entry
    gl = {k: d[k] for k in sorted(keys) if k in d}
    out["gloss"] = gl
    out["source"] = SOURCES.get(lang, "")
    out["licences"] = LICENCES
    return out


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for lang in sys.argv[1:] or ["es", "fr", "de", "en"]:
        data = build(lang)
        path = OUT / f"{lang}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        size = path.stat().st_size
        gz = len(gzip.compress(path.read_bytes()))
        print(f"{lang}: {size / 1e6:.1f} MB ({gz / 1e6:.1f} MB gzipped); "
              f"{data['lemmas'].count(chr(10)) + 1} lemma lines, {len(data['gloss'])} glosses")
