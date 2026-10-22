/* The app's introductions on two long books, which it plans 60 pages ahead: hints against the
 * greedy it used before and the exact plan over the whole book, at 8 new words a page.
 *   python app/build_data.py && node bench/pages_long.js
 */
const fs = require("fs"), path = require("path");
const R = require("../app/engine.js");
const ROOT = path.join(__dirname, "..");

for (const book of ["en-emma", "es-don-quijote"]) {
  const Lg = R.loadLanguage(JSON.parse(fs.readFileSync(path.join(ROOT, "app", "data", `${book.slice(0, 2)}.json`), "utf8")));
  const doc = R.analyze(R.paragraphsFromText(fs.readFileSync(path.join(ROOT, "books", `${book}.txt`), "utf8")), Lg);
  const pages = R.pagesOf(doc, 220);
  const lemmas = new Set();
  for (const p of doc.paragraphs) for (const s of p.sentences) for (const t of s.tokens) if (t.key !== null) lemmas.add(t.key);
  for (const n of [0, 1000]) {
    const known = new Set(R.rankedLemmas(Lg, [...lemmas].sort()).slice(0, n).filter(k => !k.startsWith("\0")));
    const {units, occ} = R.storyUnits(doc, known);
    const learned = R.rentOrBuyRule(units, occ, 6, 2);
    const hints = opts => { const t = Date.now(); const h = R.simulate(doc, pages, learned, known, 8, 0, new Set(), opts).reduce((a, x) => a + x.hinted, 0); return [h, Date.now() - t]; };
    const [greedy] = hints({greedy: true}), [app, ms] = hints({}), [exact] = hints({horizon: Infinity});
    console.log(`${book} from ${n}: ${pages.length} pages, hints: greedy ${greedy}, exact ${exact}, app ${app} `
      + `(${Math.round(100 * (greedy - app) / (greedy - exact))}% of the exact plan's gain; the whole book in ${ms} ms)`);
  }
}
