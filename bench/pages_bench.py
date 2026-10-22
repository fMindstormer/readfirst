"""Which words to introduce on which page, solved exactly and set against the app's greedy schedule.

Each word worth learning is introduced on at most one page where it occurs, at most K a page. From
that page on it is understood; before it, and if it is never introduced, each occurrence is glossed.
So introducing word w on page p avoids R(w, p) glosses, its occurrences from p on, and the schedule
with the fewest glosses is a maximum-weight b-matching of words to pages: one min-cost flow. The
most words any schedule can introduce is one max flow. A sentence is uncomfortable when more than
two of its words are neither known nor introduced by its page; the fewest uncomfortable sentences
is an integer program (CP-SAT), with the fewest glosses as a tiebreak.

    python app/build_data.py && node bench/export_pages.js && python -m bench.pages_bench
"""
import json
import sys
import time
from pathlib import Path

from ortools.graph.python import max_flow, min_cost_flow
from ortools.sat.python import cp_model

ROOT = Path(__file__).resolve().parent.parent
CAP = 2
NEVER = 1 << 30


def occurrences(pages):
    """c[w][p]: tokens on page p that contain word w."""
    c = {}
    for p, page in enumerate(pages):
        for s in page:
            for tok in s:
                for w in set(tok):
                    c.setdefault(w, {}).setdefault(p, 0)
                    c[w][p] += 1
    return c


def gains(c, learned):
    """R(w, p) for each page p where w occurs: its occurrences from p on."""
    out = {}
    for w in learned:
        rest = sum(c[w].values())
        out[w] = {}
        for p in sorted(c[w]):
            out[w][p] = rest
            rest -= c[w][p]
    return out


def evaluate(pages, at):
    """Glosses (tokens hinted, as the app counts them) and uncomfortable sentences for a schedule
    `at` (word -> page it is introduced on)."""
    hints = bad = 0
    for p, page in enumerate(pages):
        for s in page:
            for tok in s:
                if tok and not any(at.get(w) == p for w in tok) and not all(at.get(w, NEVER) < p for w in tok):
                    hints += 1
            if sum(1 for w in {w for tok in s for w in tok} if at.get(w, NEVER) > p) > CAP:
                bad += 1
    return hints, bad


def most_introductions(R, K, npages):
    """The most words any schedule can introduce: a max flow, source -> word -> page -> sink."""
    words = list(R)
    f = max_flow.SimpleMaxFlow()
    src, snk = 0, 1
    for i, w in enumerate(words):
        f.add_arc_with_capacity(src, 2 + i, 1)
        for p in R[w]:
            f.add_arc_with_capacity(2 + i, 2 + len(words) + p, 1)
    for p in range(npages):
        f.add_arc_with_capacity(2 + len(words) + p, snk, K)
    assert f.solve(src, snk) == f.OPTIMAL
    return f.optimal_flow()


def fewest_glosses(R, K, npages, bonus=0):
    """The schedule that avoids the most glosses: a min-cost flow with a bypass arc for words left
    out. With `bonus` larger than any R, it first introduces as many words as possible."""
    words = list(R)
    f = min_cost_flow.SimpleMinCostFlow()
    src, snk = 0, 1
    arcs = []
    for i, w in enumerate(words):
        f.add_arc_with_capacity_and_unit_cost(src, 2 + i, 1, 0)
        for p, r in R[w].items():
            arcs.append((f.add_arc_with_capacity_and_unit_cost(2 + i, 2 + len(words) + p, 1, -(r + bonus)), w, p))
    for p in range(npages):
        f.add_arc_with_capacity_and_unit_cost(2 + len(words) + p, snk, K, 0)
    f.add_arc_with_capacity_and_unit_cost(src, snk, len(words), 0)
    f.set_node_supply(src, len(words))
    f.set_node_supply(snk, -len(words))
    assert f.solve() == f.OPTIMAL
    return {w: p for a, w, p in arcs if f.flow(a)}


def most_comfortable(pages, R, K, seconds, start=None):
    """The fewest uncomfortable sentences (CP-SAT), then the most glosses avoided among those,
    starting from the schedule `start` (it can only improve on it). Returns the schedule, and the
    proven lower bound on uncomfortable sentences."""
    start = start or {}
    m = cp_model.CpModel()
    x = {(w, p): m.NewBoolVar("") for w in R for p in R[w]}
    for w in R:
        m.AddAtMostOne(x[w, p] for p in R[w])
    for p in range(len(pages)):
        m.Add(sum(x[w, p] for w in R if p in R[w]) <= K)
    bad = []
    for p, page in enumerate(pages):
        for s in page:
            ws = {w for tok in s for w in tok}
            if len(ws) <= CAP:
                continue
            y = m.NewBoolVar("")
            unknown = [1 - sum(x[w, q] for q in R[w] if q <= p) if w in R else 1 for w in ws]
            m.Add(sum(unknown) <= CAP + len(ws) * y)
            m.AddHint(y, sum(1 for w in ws if start.get(w, NEVER) > p) > CAP)
            bad.append(y)
    for (w, p), v in x.items():
        m.AddHint(v, start.get(w) == p)
    m.Add(sum(bad) <= evaluate(pages, start)[1])
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.num_workers = 8
    m.Minimize(sum(bad))
    solver.Solve(m)
    best, bound = round(solver.ObjectiveValue()), round(solver.BestObjectiveBound())
    m.Add(sum(bad) <= best)
    m.ClearObjective()
    m.Maximize(sum(r * x[w, p] for w in R for p, r in R[w].items()))
    m.ClearHints()
    for v in [*x.values(), *bad]:
        m.AddHint(v, solver.Value(v))
    solver.Solve(m)
    return {w: p for (w, p), v in x.items() if solver.Value(v)}, bound


def run(file, seconds):
    d = json.loads(file.read_text())
    pages, learned = d["pages"], set(d["learned"])
    c = occurrences(pages)
    R = gains(c, learned)
    rows = []
    for K in (5, 8, 12):
        g = d["greedy"][str(K)]
        greedy = {int(w): p for w, p in g["at"].items()}
        row = {"book": d["book"], "know_top": d["known"], "per_page": K, "pages": len(pages), "worth_learning": len(learned),
               "slots": K * len(pages), "greedy_ms": round(g["ms"], 1)}
        hints, bad = evaluate(pages, greedy)
        assert hints == g["hinted"], (hints, g["hinted"])            # same count as the app's simulate()
        row["greedy"] = {"introduced": len(greedy), "glosses": hints, "uncomfortable": bad}
        t = time.perf_counter()
        row["max_introductions"] = most_introductions(R, K, len(pages))
        row["max_flow_ms"] = round(1000 * (time.perf_counter() - t), 1)
        for name, bonus in (("flow", 0), ("flow_most_words", 1 + max(r for w in R for r in R[w].values()))):
            t = time.perf_counter()
            at = fewest_glosses(R, K, len(pages), bonus)
            ms = round(1000 * (time.perf_counter() - t), 1)
            hints, bad = evaluate(pages, at)
            row[name] = {"introduced": len(at), "glosses": hints, "uncomfortable": bad, "ms": ms}
            if name == "flow":
                start = at
        t = time.perf_counter()
        at, bound = most_comfortable(pages, R, K, seconds, start)
        hints, bad = evaluate(pages, at)
        row["comfort"] = {"introduced": len(at), "glosses": hints, "uncomfortable": bad, "bound": bound,
                          "ms": round(1000 * (time.perf_counter() - t))}
        row["sentences"] = sum(len(page) for page in pages)
        rows.append(row)
    return rows


if __name__ == "__main__":
    seconds = 60
    files = sorted((ROOT / "bench" / "pages").glob("*.json"))
    out = []
    for f in files:
        for r in run(f, seconds):
            out.append(r)
            g, fl, fm, co = r["greedy"], r["flow"], r["flow_most_words"], r["comfort"]
            print(f"{r['book']:20s} know={r['know_top']:4d} K={r['per_page']:2d} learn {r['worth_learning']:4d} slots {r['slots']:4d} "
                  f"max {r['max_introductions']:4d} | greedy in {g['introduced']:4d} gl {g['glosses']:5d} unc {g['uncomfortable']:4d} "
                  f"| flow in {fl['introduced']:4d} gl {fl['glosses']:5d} unc {fl['uncomfortable']:4d} {fl['ms']:.0f}ms "
                  f"| most words in {fm['introduced']:4d} gl {fm['glosses']:5d} "
                  f"| comfort unc {co['uncomfortable']:4d} (>= {co['bound']}) gl {co['glosses']:5d} {co['ms'] / 1000:.0f}s", flush=True)
    (ROOT / "bench" / "pages_results.json").write_text(json.dumps(out))
