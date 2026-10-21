"""The course: rent-or-buy is exact and keeps every sentence within the comfort limit; words are
taught before the pages that use them; the pack files are well formed."""

import itertools
import random
import sqlite3
import zipfile
from collections import Counter
from pathlib import Path

import pytest

from readfirst.course import build_course, rent_or_buy, rent_or_buy_rule, sessions_of, story_units, unlock_order, words_of
from readfirst.dictionary import compile_de, compile_es, compile_fr, compile_fr_wiktionary, short
from readfirst.pack import pack_data, write_deck, write_reader
from readfirst.text import analyze, split_clitics_es

ROOT = Path(__file__).resolve().parent.parent


def random_units(rng, n_words=9, n_sents=12):
    words = [f"w{i}" for i in range(n_words)]
    units, occ = [], Counter()
    for _ in range(n_sents):
        ws = rng.choices(words, k=rng.randint(1, 6))
        units.append(frozenset(ws)); occ.update(ws)
    return units, occ


def total(learned, occ, L):
    return L * len(learned) + sum(n for w, n in occ.items() if w not in learned)


def feasible(learned, units, cap):
    return all(len(u - learned) <= cap for u in units)


@pytest.mark.parametrize("seed", range(120))
def test_rent_or_buy_is_optimal(seed):
    rng = random.Random(seed)
    units, occ = random_units(rng)
    L, cap = rng.choice([2, 3, 6]), rng.choice([0, 1, 2])
    learned, opt = rent_or_buy(units, occ, L, cap)
    assert opt and feasible(learned, units, cap)
    words = sorted(occ)
    best = min(total(set(c), occ, L) for r in range(len(words) + 1) for c in itertools.combinations(words, r)
               if feasible(set(c), units, cap))
    assert total(learned, occ, L) == best
    rule = rent_or_buy_rule(units, occ, L, cap)
    assert feasible(rule, units, cap) and total(rule, occ, L) >= best


def test_unlock_order_is_a_permutation():
    rng = random.Random(1)
    units, occ = random_units(rng, 12, 20)
    chosen = {w for w in occ if rng.random() < 0.6}
    order = unlock_order(units, chosen, occ)
    assert sorted(order) == sorted(chosen)


@pytest.fixture(scope="module")
def marianela():
    doc, _ = analyze((ROOT / "books" / "es-marianela.txt").read_text(), "es")
    return doc


@pytest.mark.parametrize("cap", [1, 2, 3])
def test_course_keeps_its_promises(marianela, cap):
    doc = marianela
    known = {"de", "la", "que"}
    c = build_course(doc, known, cap=cap)
    taught = [w for s in c.sessions for w in s.learn]
    assert len(taught) == len(set(taught)) == len(c.learned)          # each word taught once
    first = {}
    for k, s in enumerate(c.sessions):                                 # before the first page that uses it
        for i in s.paragraphs:
            for ds in doc.paragraphs[i].sentences:
                for w in words_of(ds):
                    first.setdefault(w, k)
    where = {w: k for k, s in enumerate(c.sessions) for w in s.learn}
    assert all(where[w] == first[w] for w in where)
    for s in c.sessions:                                               # every sentence within the limit
        for i in s.paragraphs:
            for ds in doc.paragraphs[i].sentences:
                assert len({w for w in words_of(ds) if w not in known and w not in c.learned}) <= cap
    assert c.optimal
    units, occ = story_units(doc, known)
    assert sum(sum(s.glossed.values()) for s in c.sessions) == sum(n for w, n in occ.items() if w not in c.learned)


def test_sessions_cover_the_story_once(marianela):
    ss = sessions_of(marianela)
    covered = [i for s in ss for i in s.paragraphs]
    assert covered == list(range(marianela.start, len(marianela.paragraphs)))
    assert ss[0].tokens < 600                                          # the first session is about a page


def test_pack_files(marianela, tmp_path):
    c = build_course(marianela, cap=2)
    data = pack_data("Marianela", marianela, c, [])
    n = write_deck(data, tmp_path / "deck.apkg")
    assert n == len(c.learned)
    with zipfile.ZipFile(tmp_path / "deck.apkg") as z:
        z.extract("collection.anki2", tmp_path)
    db = sqlite3.connect(tmp_path / "collection.anki2")
    dues = [d for (d,) in db.execute("select due from cards order by due")]
    assert dues == list(range(1, n + 1))
    write_reader(data, tmp_path / "reader.html")
    page = (tmp_path / "reader.html").read_text()
    assert page.startswith("<!doctype html>") and "/*DATA*/" not in page
    for s in data["sessions"]:
        for ps in s["paras"]:
            for text, spans in ps:
                assert all(0 <= a < b <= len(text) for a, b, _, _ in spans)


def test_spanish_clitics():
    assert split_clitics_es("darle") == ("dar", ("le",))
    assert split_clitics_es("dármelo") == ("dar", ("me", "lo"))
    assert split_clitics_es("diciéndole") == ("diciendo", ("le",))
    assert split_clitics_es("casa") is None


def test_dictionary_parsers(tmp_path):
    es = tmp_path / "es.data"
    es.write_text("_____\nperro\npos: n\n  meta: x\n  gloss: dog\n  gloss: (slang) lazy person\n_____\n"
                  "su\npos: determiner\n  gloss: apocopic form of \"suyo\"\n_____\nsuyo\npos: pron\n  gloss: his, hers\n")
    d = compile_es(es)
    assert d["perro"].startswith("dog") and d["su"] == "his, hers"
    fr = tmp_path / "fr.tei"
    fr.write_text("<entry><form><orth>chien</orth></form><sense><cit><quote>dog</quote></cit></sense></entry>")
    assert compile_fr(fr)["chien"] == "dog"
    de = tmp_path / "de"
    de.write_text("Zimmer {n} /Zi./; Raum {m} | Zimmer {pl} :: room /rm/ | rooms\nZimmer {n} mit Frühstück :: bed and breakfast\n")
    assert compile_de(de)["Zimmer"] == "room (das)"
    assert len(short(["a" * 50, "b" * 50])) <= 80
    wk = tmp_path / "fr.tsv"
    wk.write_text("avoir|eu|aura\t<i>noun</i><br><ol><li>asset, possession</li></ol><br><i>verb</i><br><ol><li>to have</li></ol>\n"
                  "château|châteaux\t<i>noun</i><br><ol><li>castle (fortified building; estate)</li></ol>\n"
                  "douce\t<i>adj</i><br><ol><li>feminine singular of doux</li></ol>\n"
                  "doux|douce\t<i>adj</i><br><ol><li>sweet</li><li>soft</li></ol>\n"
                  "mœurs\t<i>noun</i><br><ol><li>(plural only) mores, customs</li></ol>\n"
                  "Paris\t<i>name</i><br><ol><li>Paris (capital of France)</li></ol>\n")
    d = compile_fr_wiktionary(wk)
    assert d["avoir"].startswith("to have")                # the verb before the noun homograph
    assert d["château"] == "castle"                        # no half-open bracket
    assert d["douce"] == d["doux"] == "sweet; soft"        # a form points to its word's meaning
    assert d["moeurs"] == d["mœurs"] == "mores, customs"   # both spellings, qualifier dropped
