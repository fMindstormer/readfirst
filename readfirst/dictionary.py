"""Short English glosses for a book's lemmas, from open dictionaries.

    es  Spanish-English data built from Wiktionary by doozan/spanish_data (CC BY 4.0)
    fr  French-English Wiktionary, extracted by kaikki.org and published as a tab file by
        Vuizur/Wiktionary-Dictionaries (CC BY-SA 3.0); FreeDict fra-eng (GPL 2) for the rest
    en  WordNet 3.0 definitions (English learners get English definitions)
    de  Ding German-English, Frank Richter, TU Chemnitz (GPL 2+), with each noun's gender

`python -m readfirst.dictionary fetch` downloads the sources and compiles dicts/<lang>.json.gz,
one short gloss per headword. The compiled files are not part of the repository; each keeps its
source's licence.
"""

from __future__ import annotations

import gzip
import io
import json
import re
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from urllib.request import urlopen

DICTS = Path(__file__).resolve().parent.parent / "dicts"
SOURCES = {"es": "Wiktionary via doozan/spanish_data (CC BY 4.0)",
           "fr": "Wiktionary via kaikki.org and Vuizur/Wiktionary-Dictionaries (CC BY-SA 3.0), and FreeDict fra-eng (GPL 2)",
           "en": "WordNet 3.0 (WordNet licence)", "de": "Ding de-en, TU Chemnitz (GPL 2+)"}
FORM_OF = re.compile(r"^(plural|feminine|masculine|inflection|alternative|obsolete|archaic|pronunciation|"
                     r"misspelling|apocopic|diminutive|superlative|augmentative|nonstandard|eye dialect|"
                     r"rare|dated)\b.*\bof\b", re.I)


def short(glosses, limit=60):
    """Join the first few glosses, cleaned of leading qualifiers, to at most `limit` characters."""
    out, seen = [], set()
    for g in glosses:
        g = re.sub(r"^\([^)]*\)\s*", "", g.strip()).strip(" .;")
        g = re.split(r";\s", g)[0]
        if g.count("(") > g.count(")"):           # "castle (fortified building; ...)" cut inside the brackets
            g = g[: g.rfind("(")].rstrip(" ,")
        if not g or g.lower() in seen:
            continue
        if out and len("; ".join(out + [g])) > limit:
            break
        seen.add(g.lower()); out.append(g)
    text = "; ".join(out)
    return text if len(text) <= limit + 20 else text[: limit + 17].rsplit(" ", 1)[0] + "…"


# Function words the sources lack or gloss badly, written by hand. Kept short on purpose.
OVERRIDES = {
    "es": {"a": "to; at; for", "mía": "mine, my (feminine of mío)", "tuya": "yours (feminine of tuyo)"},
    "de": {"haben": "to have", "sagen": "to say", "werden": "to become; will (future)", "können": "can, to be able to",
           "müssen": "must, to have to", "sollen": "should, to be supposed to", "wollen": "to want",
           "dürfen": "may, to be allowed to", "machen": "to make, to do", "lassen": "to let; to leave",
           "kommen": "to come", "sehen": "to see", "wissen": "to know (a fact)", "der": "the (der/die/das); who, which",
           "die": "the; who, which", "das": "the; that, which", "sich": "oneself (reflexive)", "es": "it",
           "zu": "to; too; closed", "aber": "but", "nur": "only", "noch": "still; yet; another", "schon": "already",
           "er": "he; it", "sie": "she; they; it", "ihn": "him; it", "im": "in the (in dem)", "zum": "to the (zu dem)",
           "zur": "to the (zu der)", "am": "at the, on the (an dem)", "vom": "from the (von dem)", "beim": "at the (bei dem)",
           "ins": "into the (in das)", "Eltern": "parents (die, plural)", "Herr": "Mr; gentleman; lord (der)",
           "Stand": "state, position; stall (der)", "Satz": "sentence; leap; set (der)", "Gut": "estate; goods (das)",
           "mögen": "to like; may", "Moment": "moment (der)", "Traum": "dream (der)", "Wand": "wall (die)"},
    "fr": {"m": "Mr (as M., Monsieur); metre", "bien": "well; good; very", "tout": "all, every; whole; quite",
           "même": "same; even; -self (lui-même)", "rien": "nothing; anything", "fort": "strong; very; hard",
           "point": "point; not at all (with ne)", "devoir": "must, to have to; to owe", "pouvoir": "can, to be able to", "se": "oneself (reflexive: himself, herself, themselves)", "ne": "not (with pas, plus, jamais…)",
           "y": "there; to it, about it", "peu": "little; few", "quelque": "some; a few", "ni": "nor; neither",
           "lequel": "which; who", "en": "of it, some; in", "de": "of; from", "à": "to; at; in", "le": "the; him, it",
           "un": "a, an; one", "et": "and", "que": "that; than; what", "qui": "who; which", "il": "he; it",
           "être": "to be", "avoir": "to have", "dont": "of which, whose", "où": "where; when", "si": "if; so; yes",
           "on": "one, we, people", "ce": "this, that; it", "son": "his, her, its", "dans": "in, into",
           "pour": "for; in order to", "pas": "not (with ne); step", "plus": "more; no longer (with ne)"},
    "en": {"the": "definite article", "a": "indefinite article (one)", "an": "indefinite article (one)",
           "and": "joins words or clauses", "to": "toward; marks an infinitive", "of": "belonging to; from",
           "in": "inside", "that": "the one there; introduces a clause", "it": "the thing mentioned",
           "she": "the woman or girl", "he": "the man or boy", "you": "the person addressed", "i": "the speaker",
           "her": "the woman or girl (object); hers", "his": "belonging to him", "they": "those people or things",
           "with": "accompanied by; using", "as": "in the way that; while", "for": "intended for; because",
           "but": "however", "not": "negates", "at": "in or near (a place or time)", "on": "on top of; about",
           "so": "very; therefore", "this": "the one here", "what": "which thing", "all": "every one",
           "if": "on condition that", "or": "otherwise; alternatively", "me": "the speaker (object)",
           "my": "belonging to me", "we": "the speaker and others", "him": "the man or boy (object)"},
}
ABBREV = re.compile(r"^(abbreviation|initialism|acronym|symbol|clipping|ellipsis|letter\b|(the )?name of the .*letter)", re.I)


def compile_es(path: Path) -> dict:
    """Glosses of the first part of speech that is not a proper noun, skipping abbreviations;
    "form of" glosses only when nothing else is there."""
    entries = {}
    for block in path.read_text(encoding="utf-8").split("_____\n"):
        lines = block.split("\n")
        head = lines[0].strip()
        if not head:
            continue
        groups, pos = [], None
        for ln in lines[1:]:
            if ln.startswith("pos: "):
                pos = ln[5:].strip(); groups.append((pos, []))
            m = re.match(r"  gloss: (.*)", ln)
            if m and groups:
                g = re.sub(r"\s*\(#[^)]*\)|\{\{[^}]*\}\}", "", m.group(1)).strip()
                if FORM_OF.match(g) and "; " in g and not FORM_OF.match(g.rsplit("; ", 1)[1]):
                    g = g.rsplit("; ", 1)[1]             # "inflection of él ...; him, you, it" -> "him, you, it"
                if g and not ABBREV.match(g):
                    groups[-1][1].append(g)
        good = [gs for p_, gs in groups if p_ != "prop" and gs and not all(FORM_OF.match(g) for g in gs)]
        if len(head) <= 4:                           # "a", "de", "que": the function word first
            func = [gs for p_, gs in groups if p_ in ("prep", "conj", "art", "determiner", "pron") and gs]
            good = func + [g for g in good if g not in func]
        rest = [gs for p_, gs in groups if gs]
        pick = good[0] if good else (rest[0] if rest else [])
        g = short([x for x in pick if not FORM_OF.match(x)] or pick)
        if g:
            entries[head] = g
    for head, g in list(entries.items()):           # "apocopic form of "suyo"" -> what suyo means
        m = FORM_OF.match(g) and re.search(r'of "([^"]+)"', g)
        if m and m.group(1) in entries and not FORM_OF.match(entries[m.group(1)]):
            entries[head] = entries[m.group(1)]
    for head in list(entries):                       # "Hidalgo" also answers for "hidalgo" if nothing else does
        entries.setdefault(head.lower(), entries[head])
    return entries


def compile_fr(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    entries = {}
    for e in re.findall(r"<entry>(.*?)</entry>", text, re.S):
        orth = re.findall(r"<orth>(.*?)</orth>", e)
        quotes = re.findall(r"<quote>(.*?)</quote>", e)
        if orth and quotes:
            for o in orth:
                k = o.strip().lower()
                entries[k] = short(([entries[k]] if k in entries else []) + quotes)
    return entries


def compile_fr_wiktionary(path: Path) -> dict:
    """French words with English meanings from the English Wiktionary (the kaikki.org extraction,
    as a tab file by Vuizur/Wiktionary-Dictionaries): for each headword, the senses of its first
    part of speech that is not a name, skipping abbreviations; "form of" senses only when nothing
    else is there, and then the meaning of the word they point to."""
    import html as _html
    entries, inflected = {}, {}
    for line in path.read_text(encoding="utf-8").split("\n"):
        if "\t" not in line:
            continue
        heads, body = line.split("\t", 1)
        head = heads.split("|")[0].strip()
        for f in heads.split("|")[1:]:              # its inflected forms, for words the lemmatizer misses
            if f and " " not in f and "+" not in f:
                inflected.setdefault(f.strip(), head)
        if not head or head in entries:
            continue
        groups = []
        for pos, ol in re.findall(r"<i>(.*?)</i><br><ol>(.*?)</ol>", body, re.S):
            senses = [_html.unescape(re.sub(r"<[^>]+>", "", x)).strip() for x in re.findall(r"<li>(.*?)</li>", ol, re.S)]
            groups.append((pos.strip(), [x for x in senses if x and not ABBREV.match(x)]))
        good = [(p_, gs) for p_, gs in groups if p_ != "name" and gs and not all(FORM_OF.match(g) for g in gs)]
        if re.search(r"(er|ir|re|oir)$", head):      # avoir, devoir, sourire: the verb before the noun
            good = [x for x in good if x[0] == "verb"] + [x for x in good if x[0] != "verb"]
        if len(head) <= 4:                           # "de", "que", "en": the function word first
            func = [x for x in good if x[0] in ("prep", "conj", "article", "det", "pron", "contraction")]
            good = func + [x for x in good if x not in func]
        rest = [gs for p_, gs in groups if gs]
        pick = [x for x in good[0][1] if not FORM_OF.match(x)] if good else (rest[0] if rest else [])
        if len(good) > 1:                            # bien, pas: also the first sense of the next part of speech
            second = next((x for x in good[1][1] if not FORM_OF.match(x)), None)
            if second:
                pick = pick[:1] + [second] + pick[1:]
        g = short(pick)
        if g:
            entries[head] = g
    for head, g in list(entries.items()):           # "feminine plural of doux" -> what doux means
        m = FORM_OF.match(g) and re.search(r"\bof ([^\s,;()]+)", g)
        if m and m.group(1) in entries and not FORM_OF.match(entries[m.group(1)]):
            entries[head] = entries[m.group(1)]
    for f, head in inflected.items():
        if head in entries:
            entries.setdefault(f, entries[head])
    for head in list(entries):                       # mœurs is often printed moeurs; Paris answers for paris
        entries.setdefault(head.replace("œ", "oe").replace("æ", "ae"), entries[head])
        entries.setdefault(head.lower(), entries[head])
    return entries


def fr_wiktionary_forms(path: Path) -> dict:
    """Inflected form -> headword, from the same tab file (baisa -> baiser, fussions -> être), for
    forms too rare for the lemmatizer's word list. A form listed under several headwords keeps the
    first."""
    forms = {}
    for line in path.read_text(encoding="utf-8").split("\n"):
        if "\t" not in line:
            continue
        heads = line.split("\t", 1)[0].split("|")
        head = heads[0].strip()
        for f in heads[1:]:
            f = f.strip()
            if f and f != head and " " not in f and "+" not in f:
                forms.setdefault(f, head)
    return forms


def compile_en(zip_path: Path) -> dict:
    """First (most frequent) sense of each lemma, from the WordNet database files."""
    entries = {}
    with zipfile.ZipFile(zip_path) as z:
        for pos in ("noun", "verb", "adj", "adv"):
            idx = z.read(f"wordnet/index.{pos}").decode("latin-1").splitlines()
            data = z.read(f"wordnet/data.{pos}").decode("latin-1")
            offsets = {}
            for line in data.splitlines():
                if line[:1].isdigit():
                    offsets[int(line[:8])] = line
            for line in idx:
                if line.startswith(" "):
                    continue
                parts = line.split()
                lemma, n_ptr = parts[0], int(parts[3])
                synsets = parts[4 + n_ptr + 2:]
                if not synsets:
                    continue
                gloss = offsets[int(synsets[0])].split("| ", 1)[-1].split(";")[0].strip()
                tagcnt = int(parts[4 + n_ptr + 1]) if len(parts) > 4 + n_ptr + 1 else 0
                key = lemma.replace("_", " ")
                if key not in entries or tagcnt > entries[key][1]:
                    entries[key] = (short([gloss], 70), tagcnt)
    return {k: v[0] for k, v in entries.items()}


GENDER = {"m": "der", "f": "die", "n": "das"}
FRAME = {"sich", "an", "auf", "über", "um", "mit", "zu", "von", "für", "nach", "vor", "in", "aus", "bei", "gegen", "ein"}


def compile_de(path: Path) -> dict:
    """Ding: "Zimmer {n}; Raum {m} | Zimmer {pl} :: room | rooms". A headword's gloss is the first
    sense of the entries where it stands alone as the first term (not inside a phrase), so
    idioms like "Zimmer mit Frühstück" do not leak in; nouns carry their article."""
    tag = re.compile(r"\s*(\[[^]]*\]|\{[^}]*\}|<[^>]*>|/[^/]*/|\([^)]*\))")

    def terms(side):                           # "du {ppron} (deiner; dir; dich)": split at "; " outside brackets
        out, depth, cur = [], 0, ""
        for i, ch in enumerate(side):
            depth += ch in "([{<"
            depth -= ch in ")]}>"
            if depth <= 0 and side.startswith("; ", i):
                out.append(cur)
                cur = ""
                continue
            if depth <= 0 and cur == "" and ch == " " and out:
                continue
            cur += ch
        return out + [cur]
    best: dict[str, tuple] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or " :: " not in line:
            continue
        left, right = line.split(" :: ", 1)
        de0, en0 = left.split(" | ")[0], right.split(" | ")[0]
        eng = [e.strip() for e in tag.sub("", en0).split("; ")]
        eng = [e for e in eng if e]
        if not eng:
            continue
        senses = len(left.split(" | "))
        for rank, term in enumerate(terms(de0)):
            word = tag.sub("", term).strip()
            parts = word.split(" ")              # "sich an jdn./etw. erinnern" -> erinnern
            frame = len(parts) > 1 and all(w in FRAME or "jd" in w or "etw." in w for w in parts[:-1])
            if frame:
                word = parts[-1]
            if not word or " " in word:
                continue
            g = re.search(r"\{([mfn])\}", term)
            g = g.group(1) if g else None
            # the main entry: the word first, without a qualifier like "(Gefühle)", with the most senses
            # (a main entry lists its inflected forms); a subject label like "[constr.]" decides last
            score = (rank > 0 and bool(re.search(r"\[(übtr|ugs|selten|veraltet|slang|vulg)", de0)),
                     frame, rank > 0, "(" in term, rank, -senses, "[" in term)
            if word not in best or score < best[word][0]:
                best[word] = (score, g, eng)
    out = {}
    for word, (_, g, eng) in best.items():
        text = short(eng)
        out[word] = f"{text} ({GENDER[g]})" if g and text else text
    return out


DING = "https://deb.debian.org/debian/pool/main/d/ding/trans-de-en_1.9-10_all.deb"   # Ding 1.9, packaged by Debian


def deb_member(deb: bytes, name: str) -> bytes:
    """One file from a .deb without dpkg: the package is an ar archive holding data.tar.xz."""
    pos = 8                                    # after "!<arch>\n"
    while pos < len(deb):
        member, size = deb[pos:pos + 16].decode().strip().rstrip("/"), int(deb[pos + 48:pos + 58])
        if member.startswith("data.tar"):
            with tarfile.open(fileobj=io.BytesIO(deb[pos + 60:pos + 60 + size])) as tar:
                return tar.extractfile(name).read()
        pos += 60 + size + size % 2
    raise ValueError("no data.tar in the package")


def fetch():
    DICTS.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        def sparse(repo, paths):
            d = tmp / repo.split("/")[1]
            subprocess.run(["git", "clone", "-q", "--filter=blob:none", "--no-checkout", "--depth", "1",
                            f"https://github.com/{repo}.git", str(d)], check=True)
            subprocess.run(["git", "-C", str(d), "checkout", "HEAD", "--", *paths], check=True)
            return d
        es = sparse("doozan/spanish_data", ["es-en.data"])
        save("es", compile_es(es / "es-en.data"))
        fr = sparse("freedict/fd-dictionaries", ["fra-eng/fra-eng.tei"])
        wk = sparse("Vuizur/Wiktionary-Dictionaries", ["French-English Wiktionary dictionary.tsv"])
        entries = compile_fr_wiktionary(wk / "French-English Wiktionary dictionary.tsv")
        for k, g in compile_fr(fr / "fra-eng" / "fra-eng.tei").items():   # FreeDict fills the gaps
            entries.setdefault(k, g)
        save("fr", entries)
        save("fr-forms", fr_wiktionary_forms(wk / "French-English Wiktionary dictionary.tsv"))
        (tmp / "de-en").write_bytes(deb_member(urlopen(DING).read(), "./usr/share/trans/de-en"))
        save("de", compile_de(tmp / "de-en"))
        wn = tmp / "wordnet.zip"
        wn.write_bytes(urlopen("https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/corpora/wordnet.zip").read())
        save("en", compile_en(wn))


def save(lang, entries):
    with gzip.open(DICTS / f"{lang}.json.gz", "wt", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{lang}: {len(entries):,} headwords", file=sys.stderr)


_cache: dict[str, dict] = {}


def load(lang: str) -> dict:
    if lang not in _cache:
        p = DICTS / f"{lang}.json.gz"
        _cache[lang] = json.loads(gzip.open(p, "rt", encoding="utf-8").read()) if p.exists() else {}
        _cache[lang].update(OVERRIDES.get(lang, {}))
    return _cache[lang]


def gloss(lang: str, lemma: str, forms=()) -> str:
    """A short gloss for the lemma, else for one of its written forms; "" if none is known."""
    d = load(lang)
    for k in (lemma, lemma.lower(), *forms, *(f.lower() for f in forms)):
        if k in d:
            return d[k]
    return ""


def wiktionary(lang: str, lemma: str) -> str:
    from urllib.parse import quote
    section = {"es": "Spanish", "fr": "French", "de": "German", "en": "English"}.get(lang, "")
    return f"https://en.wiktionary.org/wiki/{quote(lemma)}#{section}"


if __name__ == "__main__":
    if sys.argv[1:] == ["fetch"]:
        fetch()
    else:
        print(__doc__)
