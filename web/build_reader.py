"""The demo study pack page: Marianela, from zero, balanced comfort (bare page, for hosting)."""
from pathlib import Path

from readfirst.course import build_course
from readfirst.pack import pack_data, tradeoff, write_reader
from readfirst.text import analyze

ROOT = Path(__file__).resolve().parent.parent
doc, _ = analyze((ROOT / "books" / "es-marianela.txt").read_text(), "es")
course = build_course(doc, cap=2)
data = pack_data("Marianela", doc, course, tradeoff(doc, set()))
write_reader(data, ROOT / "web" / "marianela-reader.html", standalone=False)
print((ROOT / "web" / "marianela-reader.html").stat().st_size // 1024, "KB")
