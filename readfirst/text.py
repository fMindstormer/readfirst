"""From a book to sentences over lemmas.

A sentence is readable once the learner knows every lemma in it. Names (words the text never writes
in lowercase) and numbers are free. Identical lemma sets are merged into one weighted sentence.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import simplemma

LETTERS = r"[^\W\d_]"
TOKEN = re.compile(rf"{LETTERS}+(?:['’]{LETTERS}+)*")
OPENERS = "¿¡«“\"'(—–-‘"
CLOSERS = "\"'»”’)]"
# end of sentence: . ! ? … then closing quotes, space, then (opening marks and) an uppercase letter
SPLIT = re.compile(rf"(?<=[.!?…])([{re.escape(CLOSERS)}]*)\s+(?=[{re.escape(OPENERS)}]*[^\W\d_](?<=[A-ZÀ-ÖØ-Þ]))")
ABBREV = {"mr", "mrs", "ms", "dr", "st", "sr", "sra", "srta", "dña", "d", "mme", "mlle", "m", "hr", "fr", "nr",
          "etc", "vs", "jr", "prof", "gen", "capt", "col", "lt", "rev", "hon", "z.b", "u.s", "no"}
ELISION_FR = {"l": "le", "d": "de", "j": "je", "qu": "que", "n": "ne", "s": "se", "c": "ce", "m": "me", "t": "te",
              "jusqu": "jusque", "lorsqu": "lorsque", "puisqu": "puisque", "quoiqu": "quoique", "presqu": "presque"}
NOT_NAMES = {"I", "I'm", "I'll", "I've", "I'd", "OK", "O"}
NOUN_CAPS = {"de"}
# personal pronouns stay separate words: lemmatizers fold them together ("usted" -> "tú", "te" -> "le")
KEEP = {
    "es": set("yo me mí conmigo tú te ti contigo usted ustedes él ella ello lo la le se sí consigo "
              "nosotros nosotras nos vosotros vosotras os ellos ellas los las les".split()),
    "fr": set("je me moi tu te toi il elle on le la lui se soi nous vous ils elles les leur eux en y".split()),
    "de": set("ich mich mir du dich dir er ihn ihm sie es sich wir uns ihr euch ihnen".split()),
    "en": set("i me you he him she her it we us they them".split()),
}                      # languages that capitalise common nouns: no automatic names


def strip_gutenberg(text: str) -> str:
    m = re.search(r"\*\*\*\s*START OF (THE|THIS) PROJECT GUTENBERG[^\n]*\n", text)
    if m:
        text = text[m.end():]
    m = re.search(r"\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG|^End of (the )?Project Gutenberg", text, re.M)
    if m:
        text = text[:m.start()]
    return text


def split_sentences(text: str) -> list[str]:
    out = []
    for para in re.split(r"\n\s*\n", text):
        out.extend(split_paragraph(re.sub(r"\s+", " ", para).strip()))
    return out


def split_paragraph(para: str) -> list[str]:
    out = []
    if para:
        start = 0
        for m in SPLIT.finditer(para):
            before = para[start:m.start()]
            last = re.search(r"(\w+)\.$", before)
            if last and (last.group(1).lower() in ABBREV or len(last.group(1)) == 1 and last.group(1).isupper()):
                continue                  # "Mr. Smith", "J. Smith": not a sentence end
            out.append(para[start:m.start() + len(m.group(1))].strip())
            start = m.end()
        out.append(para[start:].strip())
    return [s for s in out if s]


def token_spans(sentence: str, lang: str) -> list[tuple[str, int, int]]:
    """Tokens with their character spans in the sentence; French elisions split after the apostrophe."""
    out = []
    for m in TOKEN.finditer(sentence):
        t, a = m.group(), m.start()
        t = t.replace("’", "'")
        if lang in ("fr", "it", "ca") and "'" in t:
            while "'" in t:
                head, _, tail = t.partition("'")
                out.append((head + "'", a, a + len(head) + 1))
                a += len(head) + 1
                t = tail
            if t:
                out.append((t, a, a + len(t)))
        else:
            out.append((t, a, m.end()))
    return out


def tokens(sentence: str, lang: str) -> list[str]:
    return [t for t, _, _ in token_spans(sentence, lang)]


@dataclass
class Sentence:
    text: str
    words: frozenset          # lemma keys
    count: int = 1            # identical lemma sets merged
    pairs: tuple = ()         # (token, lemma or None for a name), in order


@dataclass
class Book:
    lang: str
    sentences: list[Sentence]
    free: int                                     # sentences with no word to learn (all names)
    token_count: Counter                          # lemma -> occurrences in the text
    surface: dict                                 # lemma -> most common written form
    names: set = field(default_factory=set)


@dataclass
class Token:
    text: str
    start: int                # character span in the sentence
    end: int
    key: str | None           # lemma; None for a name (free to read)
    extra: tuple = ()         # further words written into the same token: "darle" is dar + le


@dataclass
class DocSentence:
    text: str
    tokens: list


@dataclass
class Paragraph:
    sentences: list
    heading: bool


@dataclass
class Doc:
    """The book in reading order. `start` is the first paragraph of the main text (front matter
    such as a title page or a table of contents comes before it)."""
    lang: str
    paragraphs: list
    start: int
    names: set


HEAD_WORD = re.compile(r"^(chapter|chapitre|cap[ií]tulo|kapitel|book|part|libro|parte|livre|teil|tome|acte?)\b", re.I)
ROMAN = re.compile(r"^([IVXLC]+)\.?(?:\s+(.*))?$")


CHAPTER_WORD = re.compile(r"^(chapter|chapitre|cap[ií]tulo|kapitel)\b", re.I)


def is_heading(par: str) -> bool:
    words = TOKEN.findall(par)
    if not par or par[-1] in "?!\"»”" or len(words) > (25 if HEAD_WORD.match(par) else 12):
        return False
    if HEAD_WORD.match(par):
        return True
    m = ROMAN.match(par)
    if not m:
        return False
    rest = m.group(2)
    return not rest or not rest[0].islower() and not (len(m.group(1)) == 1 and rest.split()[0][:1].islower())


def analyze(text: str, lang: str, names: bool | None = None) -> tuple[Doc, "callable"]:
    """Split the book into paragraphs and sentences, decide which capitalised words are names, and
    return the document with every token lemmatised (plus the lemmatiser, for reuse)."""
    text = unicodedata.normalize("NFC", strip_gutenberg(text))
    raw = [p for p in re.split(r"\n\s*\n", text)]
    paras = []
    for block in raw:
        flat = re.sub(r"\s+", " ", block).strip()
        if not flat:
            continue
        lines = block.strip().count("\n") + 1
        head = is_heading(flat) and (lines == 1 or lines <= 3 and bool(HEAD_WORD.match(flat)))
        paras.append((flat, head, [(s, token_spans(s, lang)) for s in split_paragraph(flat)]))

    lower_seen, cap_mid = set(), set()
    for _, _, sents in paras:
        for _, spans in sents:
            for i, (t, _, _) in enumerate(spans):
                if t[0].islower():
                    lower_seen.add(t.lower())
                elif i > 0:
                    cap_mid.add(t)
    if names is None:
        names = lang not in NOUN_CAPS
    name_set = {t for t in cap_mid if names and t.lower() not in lower_seen and len(t) > 1
                and t not in NOT_NAMES and not t.isupper()}
    key = _lemmatizer(lang, lower_seen, cap_mid)

    out = []
    for flat, head, sents in paras:
        ds = []
        for s, spans in sents:
            toks = []
            for i, (t, a, b) in enumerate(spans):
                if t in name_set:
                    toks.append(Token(t, a, b, None))
                    continue
                split = split_clitics_es(t) if lang == "es" else None
                if split:
                    toks.append(Token(t, a, b, key(split[0], False), split[1]))
                else:
                    toks.append(Token(t, a, b, key(t, i == 0)))
            ds.append(DocSentence(s, toks))
        out.append(Paragraph(ds, head))
    return Doc(lang, out, _main_start(out), name_set), key


def _narrative(p) -> bool:
    toks = [t.text for s in p.sentences for t in s.tokens]
    return not p.heading and len(toks) >= 40 and sum(t[0].islower() for t in toks) >= 0.6 * len(toks)


def _main_start(pars) -> int:
    """Where the story starts: the first chapter heading followed by prose (a table of contents has
    headings but no prose under them); else the first heading followed by prose; else the first
    paragraph of prose."""
    def followed_by_prose(i):
        for q in pars[i + 1:]:
            if q.heading:
                return False
            if _narrative(q):
                return True
        return False
    texts = [" ".join(s.text for s in p.sentences) for p in pars]
    for pick in (lambda i: CHAPTER_WORD.match(texts[i]), lambda i: True):
        for i, p in enumerate(pars):
            if p.heading and pick(i) and followed_by_prose(i):
                return i
    return next((i for i, p in enumerate(pars) if _narrative(p)), 0)


CLITICS_ES = ("nos", "les", "los", "las", "me", "te", "se", "lo", "la", "le", "os")
UNACCENT = str.maketrans("áéíóú", "aeiou")


def split_clitics_es(word: str):
    """'darle' -> ('dar', ('le',)); 'diciéndoselo' -> ('diciendo', ('se', 'lo')); None if it is not
    an infinitive, gerund or imperative with pronouns attached."""
    w = word.lower()
    if simplemma.is_known(w, lang="es"):
        return None
    found = []
    for _ in range(2):
        for c in CLITICS_ES:
            if w.endswith(c) and len(w) - len(c) >= 3:
                stem = w[: -len(c)].translate(UNACCENT)
                found.insert(0, c)
                w = w[: -len(c)]
                if re.search(r"(ar|er|ir|ír|ando|iendo|yendo)$", stem) and simplemma.is_known(stem, lang="es"):
                    return stem, tuple(found)
                break
        else:
            break
    return None


def _lemmatizer(lang, lower_seen, cap_mid):
    cache: dict[tuple[str, bool], str] = {}

    def key(t: str, initial: bool) -> str:
        k = (t, initial)
        if k in cache:
            return cache[k]
        if t.lower() in KEEP.get(lang, ()):
            r = t.lower()
        elif lang in ("fr", "it", "ca") and t.endswith("'"):
            h = t[:-1].lower()
            r = ELISION_FR.get(h, h) if lang == "fr" else simplemma.lemmatize(h, lang=lang)
        elif lang in NOUN_CAPS:
            w = t
            if t.isupper() and len(t) > 1:
                w = t.capitalize()
            if initial and t[0].isupper() and t.lower() in lower_seen and t not in cap_mid:
                w = t.lower()               # "Als" at the start of a sentence is "als"
            r = simplemma.lemmatize(w, lang=lang)
            if not w[0].isupper():
                r = r.lower()
        else:
            r = simplemma.lemmatize(t.lower(), lang=lang).lower()
        cache[k] = r
        return r
    return key


def book_from_doc(doc: Doc, min_tokens: int = 3) -> Book:
    """The sentences the foundation plan optimises over: 3+ tokens, identical lemma sets merged."""
    merged: dict[frozenset, Sentence] = {}
    order, free = [], 0
    freq, forms = Counter(), defaultdict(Counter)
    for p in doc.paragraphs:
        for ds in p.sentences:
            if len(ds.tokens) < min_tokens:
                continue
            ws = set()
            pairs = tuple((t.text, t.key) for t in ds.tokens)
            for t in ds.tokens:
                if t.key is not None:
                    ws.add(t.key)
                    freq[t.key] += 1
                    forms[t.key][t.text if doc.lang in NOUN_CAPS else t.text.lower()] += 1
                    for x in t.extra:
                        ws.add(x); freq[x] += 1; forms[x][x] += 1
            if not ws:
                free += 1
                continue
            fs = frozenset(ws)
            if fs in merged:
                merged[fs].count += 1
            else:
                merged[fs] = Sentence(ds.text, fs, 1, pairs)
                order.append(fs)
    surface = {k: c.most_common(1)[0][0] for k, c in forms.items()}
    return Book(doc.lang, [merged[f] for f in order], free, freq, surface, doc.names)


def build(text: str, lang: str, min_tokens: int = 3, names: bool | None = None) -> Book:
    doc, _ = analyze(text, lang, names)
    return book_from_doc(doc, min_tokens)


def _old_build(text: str, lang: str, min_tokens: int = 3, names: bool | None = None) -> Book:
    text = unicodedata.normalize("NFC", strip_gutenberg(text))
    sents = split_sentences(text)
    toks = [tokens(s, lang) for s in sents]

    lower_seen, cap_mid = set(), set()
    for ts in toks:
        for i, t in enumerate(ts):
            if t[0].islower():
                lower_seen.add(t.lower())
            elif i > 0:
                cap_mid.add(t)
    if names is None:
        names = lang not in NOUN_CAPS
    name_set = {t for t in cap_mid if names and t.lower() not in lower_seen and len(t) > 1
                and t not in NOT_NAMES and not t.isupper()}

    cache: dict[tuple[str, bool], str] = {}

    def key(t: str, initial: bool) -> str:
        k = (t, initial)
        if k in cache:
            return cache[k]
        if t.lower() in KEEP.get(lang, ()):
            r = t.lower()
        elif lang in ("fr", "it", "ca") and t.endswith("'"):
            h = t[:-1].lower()
            r = ELISION_FR.get(h, h) if lang == "fr" else simplemma.lemmatize(h, lang=lang)
        elif lang in NOUN_CAPS:
            w = t
            if t.isupper() and len(t) > 1:
                w = t.capitalize()
            if initial and t[0].isupper() and t.lower() in lower_seen and t not in cap_mid:
                w = t.lower()               # "Als" at the start of a sentence is "als"
            r = simplemma.lemmatize(w, lang=lang)
            if not w[0].isupper():
                r = r.lower()
        else:
            r = simplemma.lemmatize(t.lower(), lang=lang).lower()
        cache[k] = r
        return r

    merged: dict[frozenset, Sentence] = {}
    order = []
    free = 0
    freq, forms = Counter(), defaultdict(Counter)
    for s, ts in zip(sents, toks):
        if len(ts) < min_tokens:
            continue
        ws, pairs = set(), []
        for i, t in enumerate(ts):
            if t in name_set:
                pairs.append((t, None))
                continue
            k = key(t, i == 0)
            pairs.append((t, k))
            ws.add(k)
            freq[k] += 1
            forms[k][t if lang in NOUN_CAPS else t.lower()] += 1
        if not ws:
            free += 1
            continue
        fs = frozenset(ws)
        if fs in merged:
            merged[fs].count += 1
        else:
            merged[fs] = Sentence(s, fs, 1, tuple(pairs))
            order.append(fs)
    surface = {k: c.most_common(1)[0][0] for k, c in forms.items()}
    return Book(lang, [merged[f] for f in order], free, freq, surface, name_set)
