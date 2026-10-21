"""Assemble the app, the page with the engine inlined, its data and the sample books, twice:

    app/dist/   for publishing as a Claude artifact (the host adds the document skeleton)
    app/site/   a static site for any web server (complete HTML document)

    python app/build_app.py
"""
import shutil
from pathlib import Path

APP = Path(__file__).resolve().parent
DIST = APP / "dist"
SITE = APP / "site"
SKELETON = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"></head><body>')
SAMPLES = ["es-marianela.txt", "fr-candide.txt", "de-die-verwandlung.txt", "en-alice.txt"]


def main():
    page = (APP / "src" / "index.html").read_text(encoding="utf-8")
    engine = (APP / "engine.js").read_text(encoding="utf-8")
    assert "/*ENGINE*/" in page
    page = page.replace("/*ENGINE*/", engine.replace("</script", "<\\/script"))
    for out, html in ((DIST, page), (SITE, SKELETON + page + "</body></html>")):
        (out / "data").mkdir(parents=True, exist_ok=True)
        (out / "samples").mkdir(exist_ok=True)
        (out / "index.html").write_text(html, encoding="utf-8")
        for f in (APP / "data").glob("*.json"):
            shutil.copy(f, out / "data" / f.name)
        for name in SAMPLES:
            shutil.copy(APP.parent / "books" / name, out / "samples" / name)
        print("wrote", out, sum(f.stat().st_size for f in out.rglob("*") if f.is_file()) // 1000, "kB")


if __name__ == "__main__":
    main()
