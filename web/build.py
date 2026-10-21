"""Embed the benchmark results into the page."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
res = json.loads((ROOT / "bench" / "results.json").read_text())
slim = []
for r in res:
    slim.append({k: r[k] for k in ("book", "title", "lang", "know_top", "sentences", "words", "known")} | {
        "needed": {k: r["needed"][k] for k in ("proof", "plan", "book_freq")},
        "curve": {k: r["curve"][k] for k in ("k", "bound", "plan", "book_freq")},
        "plan": [{k: p[k] for k in ("step", "lemma", "form", "example", "unknown_in_example", "readable")} for p in r["plan"]]})
course = [r for r in json.loads((ROOT / "bench" / "course_results.json").read_text()) if r["book"] == "es-marianela"]
html = (ROOT / "web" / "template.html").read_text().replace("/*DATA*/null", json.dumps(slim, ensure_ascii=False, separators=(",", ":")))
html = html.replace("/*COURSE*/null", json.dumps(course, separators=(",", ":")))
(ROOT / "web" / "index.html").write_text(html)
print(len(html) // 1024, "KB")
