/* Invariants of reading pages and in-context introductions, on the four sample books.
 *   node app/test/check_pages.js
 */
const fs = require("fs"), path = require("path");
const R = require("../engine.js");
const APP = path.join(__dirname, "..");
const BOOKS = {es: "es-marianela.txt", fr: "fr-candide.txt", de: "de-die-verwandlung.txt", en: "en-alice.txt"};
let failed = 0;
const check = (ok, msg) => { if (!ok) { failed++; console.log("  FAIL " + msg); } };
for (const [lang, file] of Object.entries(BOOKS)) {
  const Lg = R.loadLanguage(JSON.parse(fs.readFileSync(path.join(APP, "data", `${lang}.json`), "utf8")));
  const doc = R.analyze(R.paragraphsFromText(fs.readFileSync(path.join(APP, "..", "books", file), "utf8")), Lg);
  const pages = R.pagesOf(doc, 220);
  // every sentence of the story on exactly one page, in order
  const order = [];
  for (const pg of pages) for (const [pi, a, b] of pg.pieces) for (let k = a; k < b; k++) order.push(pi * 100000 + k);
  const want = [];
  for (let pi = doc.start; pi < doc.paragraphs.length; pi++) doc.paragraphs[pi].sentences.forEach((_, k) => want.push(pi * 100000 + k));
  check(JSON.stringify(order) === JSON.stringify(want), `${file}: pages do not cover the story exactly once`);
  const sizes = pages.map(p => p.tokens).sort((a, b) => a - b);
  const longest = Math.max(...pages.map(pg => Math.max(...[...R.pageSentences(doc, pg)].map(s => s.tokens.length))));
  check(sizes[sizes.length - 1] <= 1.6 * 220 + longest, `${file}: a page of ${sizes[sizes.length - 1]} words`);
  // introductions
  for (const [label, n] of [["zero", 0], ["1,000 words", 1000]]) {
    const lemmas = new Set();
    for (const p of doc.paragraphs) for (const s of p.sentences) for (const t of s.tokens) if (t.key !== null) lemmas.add(t.key);
    const known = new Set(R.rankedLemmas(Lg, [...lemmas].sort()).slice(0, n).filter(k => !k.startsWith("\0")));
    const {units, occ} = R.storyUnits(doc, known);
    const learned = R.rentOrBuyRule(units, occ, 6, 2);
    const met = new Set(), rem = R.occurrencesFrom(doc, pages, 0);
    let maxNew = 0, total = 0;
    pages.forEach((pg, p) => {
      const fresh = R.introductionsOn(doc, pg, learned, w => known.has(w) || met.has(w), 8, rem);
      for (const s of R.pageSentences(doc, pg)) for (const w of R.wordsOf(s)) rem.set(w, rem.get(w) - 1);
      maxNew = Math.max(maxNew, fresh.length);
      const onPage = new Set([...R.pageSentences(doc, pg)].flatMap(s => R.wordsOf(s)));
      check(fresh.every(w => onPage.has(w) && !met.has(w) && !known.has(w)), `${file}: page ${p} introduces a word it lacks or one already met`);
      fresh.forEach(w => met.add(w)); total += fresh.length;
    });
    const sim = R.simulate(doc, pages, learned, known, 8);
    check(sim.reduce((a, x) => a + x.introduced, 0) === total, `${file}: simulation and page walk disagree`);
    const missed = [...learned].filter(w => !met.has(w) && !known.has(w)).length;
    const q = i => sim[Math.min(sim.length - 1, i)].known;
    console.log(`${file} from ${label}: ${pages.length} pages (median ${sizes[sizes.length >> 1]} words), at most ${maxNew} new words a page, `
      + `${total} introduced of ${learned.size} worth learning (${missed} never get a free slot); words known: `
      + `page 1 ${(100 * q(0)).toFixed(0)}%, page 20 ${(100 * q(19)).toFixed(0)}%, middle ${(100 * q(sim.length >> 1)).toFixed(0)}%, end ${(100 * q(sim.length - 1)).toFixed(0)}%`);
    check(maxNew <= 8, `${file}: more than 8 new words on a page`);
  }
}
console.log(failed ? `${failed} failed` : "all page checks pass");
process.exit(failed ? 1 : 0);
