/* The app's page-introduction problem on the four sample books, exported for bench/pages_bench.py:
 * pages of sentences of tokens (the word ids in each token that the reader does not already know),
 * the words worth learning, and the app's own greedy schedule at 5, 8 and 12 new words a page.
 *   python app/build_data.py && node bench/export_pages.js      -> bench/pages/<book>-<known>.json
 */
const fs = require("fs"), path = require("path");
const R = require("../app/engine.js");
const ROOT = path.join(__dirname, "..");
const BOOKS = {es: "es-marianela", fr: "fr-candide", de: "de-die-verwandlung", en: "en-alice"};
fs.mkdirSync(path.join(__dirname, "pages"), {recursive: true});

for (const [lang, book] of Object.entries(BOOKS)) {
  const Lg = R.loadLanguage(JSON.parse(fs.readFileSync(path.join(ROOT, "app", "data", `${lang}.json`), "utf8")));
  const doc = R.analyze(R.paragraphsFromText(fs.readFileSync(path.join(ROOT, "books", `${book}.txt`), "utf8")), Lg);
  const pages = R.pagesOf(doc, 220);
  const lemmas = new Set();
  for (const p of doc.paragraphs) for (const s of p.sentences) for (const t of s.tokens) if (t.key !== null) lemmas.add(t.key);
  for (const n of [0, 1000]) {
    const known = new Set(R.rankedLemmas(Lg, [...lemmas].sort()).slice(0, n).filter(k => !k.startsWith("\0")));
    const {units, occ} = R.storyUnits(doc, known);
    const learned = R.rentOrBuyRule(units, occ, 6, 2);
    const ids = new Map(), words = [];
    const id = w => { if (!ids.has(w)) { ids.set(w, words.length); words.push(w); } return ids.get(w); };
    const out = pages.map(pg => [...R.pageSentences(doc, pg)].map(s => s.tokens.filter(t => t.key !== null)
      .map(t => [t.key, ...t.extra].filter(w => !known.has(w)).map(id))));
    const greedy = {};
    for (const perPage of [5, 8, 12]) {
      const t0 = process.hrtime.bigint();
      const met = new Set(), rem = R.occurrencesFrom(doc, pages, 0), at = {};
      pages.forEach((pg, p) => {
        for (const w of R.introductionsOn(doc, pg, learned, w => known.has(w) || met.has(w), perPage, rem)) { met.add(w); at[ids.get(w)] = p; }
        for (const s of R.pageSentences(doc, pg)) for (const w of R.wordsOf(s)) rem.set(w, rem.get(w) - 1);
      });
      const ms = Number(process.hrtime.bigint() - t0) / 1e6;
      const hinted = R.simulate(doc, pages, learned, known, perPage).reduce((a, x) => a + x.hinted, 0);
      greedy[perPage] = {at, ms, hinted};
    }
    const file = path.join(__dirname, "pages", `${book}-${n}.json`);
    fs.writeFileSync(file, JSON.stringify({book, lang, known: n, words, learned: [...learned].map(id), pages: out, greedy}));
    console.log(`${book} know=${n}: ${pages.length} pages, ${words.length} unknown words, ${learned.size} worth learning`);
  }
}
