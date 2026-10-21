"""A course built from one book: read it in order, a few pages per session, learning just before
each session the words worth learning and glossing the rest.

Which words are worth learning is a rent-or-buy decision, made for the whole book at once. Each
unknown word is either learned (bought: a flashcard, cost `learn_cost`) or glossed every time it
appears (rented: one look-up per occurrence). With the whole book known in advance, a word alone
would be bought exactly when it appears `learn_cost` times or more. What couples the words is
comfort: no sentence may need more than `cap` glosses. The exact optimum is a small integer
program (OR-Tools CP-SAT):

    minimise   learn_cost * #learned  +  #occurrences of words not learned
    subject to for every sentence s: #(unknown words of s not learned) <= cap

A learned word is taught right before the session where it first appears, so the rest of the book
reviews it. Within a session's list, words are studied in the order that makes the coming pages
readable soonest (the same greedy that orders the book-wide plan), so the learner can already read
more and more of those pages while studying.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from .order import Instance, greedy
from .text import Doc

COMFORT = {"comfortable": 1, "balanced": 2, "fast": 3}


@dataclass
class Session:
    index: int
    title: str
    paragraphs: range                      # indices into doc.paragraphs
    tokens: int                            # words to read (names included)
    learn: list = field(default_factory=list)          # lemmas to study first, in study order
    glossed: Counter = field(default_factory=Counter)  # lemma -> occurrences glossed in this session
    sentences: int = 0
    sentences_glossed: int = 0


@dataclass
class Course:
    lang: str
    known: set
    sessions: list
    learned: set
    daily: int
    cap: int
    learn_cost: float
    optimal: bool

    def days(self) -> int:
        """Study `daily` words a day; read a session on the day its list is done (one per day)."""
        return sum(max(1, -(-len(s.learn) // self.daily)) for s in self.sessions)

    def start_day(self) -> int:
        return max(1, -(-len(self.sessions[0].learn) // self.daily)) if self.sessions else 0

    def stats(self) -> dict:
        tok = sum(s.tokens for s in self.sessions)
        g = sum(sum(s.glossed.values()) for s in self.sessions)
        return {"sessions": len(self.sessions), "taught": len(self.learned), "days": self.days(),
                "start_day": self.start_day(), "glosses": g, "glosses_per_page": round(250 * g / max(1, tok), 2),
                "coverage": round(1 - g / max(1, tok), 4), "tokens": tok, "optimal": self.optimal,
                "sentences_with_gloss": round(sum(s.sentences_glossed for s in self.sessions)
                                              / max(1, sum(s.sentences for s in self.sessions)), 3)}


def sessions_of(doc: Doc, target: int = 1000, min_size: int = 200, first: int = 250) -> list[Session]:
    """Cut at paragraph breaks, and at chapter headings when the session so far is long enough.
    Sessions grow: about one page (`first` words), then two, three, up to about four pages
    (`target`), so the learner reaches the story early. A long paragraph stays whole."""
    out, start, size, title = [], doc.start, 0, ""
    pars = doc.paragraphs

    def close(end):
        nonlocal start, size
        if end > start:
            out.append(Session(len(out), title, range(start, end), size))
        start, size = end, 0

    chapter = ""
    for i in range(doc.start, len(pars)):
        p = pars[i]
        if p.heading:
            if size >= min_size:
                close(i)
            chapter = " ".join(s.text for s in p.sentences)
            if size == 0:
                title = chapter
            continue
        if size == 0 and not title:
            title = chapter
        size += sum(len(s.tokens) for s in p.sentences)
        if size >= min(target, first * (len(out) + 1)):
            close(i + 1)
            title = chapter + " (cont.)" if chapter else ""
    close(len(pars))
    for k, s in enumerate(out):
        if not s.title:
            s.title = f"Part {k + 1}"
    return out


def words_of(ds) -> list:
    """Every word to know in a sentence, in order, with repeats (names are free)."""
    out = []
    for t in ds.tokens:
        if t.key is not None:
            out.append(t.key)
            out.extend(t.extra)
    return out


def story_units(doc: Doc, known: set):
    """Unknown-word sets of the story's sentences, and each unknown word's occurrences."""
    units, occ = [], Counter()
    for p in doc.paragraphs[doc.start:]:
        for ds in p.sentences:
            ws = [w for w in words_of(ds) if w not in known]
            units.append(frozenset(ws))
            occ.update(ws)
    return units, occ


def rent_or_buy(units, occ, learn_cost: float = 6, cap: int = 2, time_limit: float = 120.0):
    """The exact choice of words to learn. Returns (learned set, proven optimal)."""
    words = sorted(occ)
    m = cp_model.CpModel()
    x = {w: m.NewBoolVar(w) for w in words}
    for u in set(units):
        if len(u) > cap:
            m.Add(sum(x[w] for w in u) >= len(u) - cap)
    scale = 10
    m.Minimize(sum(int(round(learn_cost * scale)) * x[w] + scale * occ[w] * (1 - x[w]) for w in words))
    s = cp_model.CpSolver()
    s.parameters.max_time_in_seconds = time_limit
    s.parameters.num_workers = 8
    st = s.Solve(m)
    assert st in (cp_model.OPTIMAL, cp_model.FEASIBLE), s.StatusName(st)
    return {w for w in words if s.Value(x[w])}, st == cp_model.OPTIMAL


def rent_or_buy_rule(units, occ, learn_cost: float = 6, cap: int = 2):
    """The obvious rule, for comparison: learn every word met `learn_cost` times or more; then,
    while a sentence still needs more than `cap` glosses, learn its most frequent unknown word."""
    learned = {w for w, n in occ.items() if n >= learn_cost}
    for u in units:
        rest = sorted(u - learned, key=lambda w: (-occ[w], w))
        while len(rest) > cap:
            learned.add(rest.pop(0))
    return learned


def unlock_order(units, chosen, freq):
    """Study order for a session's list: next, the word that makes the most of the session's
    sentences readable (all their words learned or glossed), ties to the more frequent word."""
    if not chosen:
        return []
    ch = set(chosen)
    sets = [frozenset(u & ch) for u in units if u & ch]
    inst = Instance.from_sets(sets)
    order = [inst.words[i] for i in greedy(inst, Counter({w: freq[w] for w in inst.words}))]
    return order + sorted(ch - set(order), key=lambda w: (-freq[w], w))


def build_course(doc: Doc, known=(), cap: int = 2, learn_cost: float = 6, daily: int = 15,
                 method: str = "exact", sessions: list | None = None) -> Course:
    known = set(known)
    units, occ = story_units(doc, known)
    if method == "exact":
        learned, optimal = rent_or_buy(units, occ, learn_cost, cap)
    else:
        learned, optimal = rent_or_buy_rule(units, occ, learn_cost, cap), False
    sessions = sessions if sessions is not None else sessions_of(doc)
    seen = set(known)
    for s in sessions:
        s_units = []
        for i in s.paragraphs:
            for ds in doc.paragraphs[i].sentences:
                ws = words_of(ds)
                s_units.append(frozenset(w for w in ws if w not in known))
                hit = False
                for w in ws:
                    if w not in known and w not in learned:
                        s.glossed[w] += 1
                        hit = True
                s.sentences += 1
                s.sentences_glossed += hit
        new = {w for u in s_units for w in u if w in learned and w not in seen}
        s.learn = unlock_order(s_units, new, occ)
        seen |= new
    return Course(doc.lang, known, sessions, learned, daily, cap, learn_cost, optimal)
