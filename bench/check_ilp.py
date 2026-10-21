"""Independent check of a claimed minimum with an exact integer program (OR-Tools CP-SAT):
with one word fewer than the claim, no choice of words reaches the target."""
import sys

from ortools.sat.python import cp_model

from readfirst.order import Instance, envelope
from readfirst.text import build

name, pct = sys.argv[1], float(sys.argv[2])
book = build(open(f"books/{name}.txt").read(), name[:2])
inst = Instance.from_book(book)
W = inst.total
target = W * pct / 100
claim = envelope(inst).words_needed(target)
m = cp_model.CpModel()
x = [m.NewBoolVar(f"x{i}") for i in range(len(inst.words))]
y = [m.NewBoolVar(f"y{j}") for j in range(len(inst.edges))]
for j, e in enumerate(inst.edges):
    for w in e:
        m.AddImplication(y[j], x[w])
m.Add(sum(x) <= claim - 1)
m.Maximize(sum(int(w) * yj for w, yj in zip(inst.weights, y)))
s = cp_model.CpSolver(); s.parameters.max_time_in_seconds = 600; s.parameters.num_workers = 8
st = s.Solve(m)
print(f"{name}: target {target:.1f} of {W}; claimed minimum {claim} words; with {claim - 1} words CP-SAT "
      f"best {s.ObjectiveValue():.0f}, proven upper bound {s.BestObjectiveBound():.0f}, status {s.StatusName(st)}")
print("CONFIRMED" if inst.base + s.BestObjectiveBound() < target else "NOT CONFIRMED")
