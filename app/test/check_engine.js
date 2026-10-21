/* Check the JavaScript engine against the Python implementation (app/test/ref-*.json).
 *
 *   node app/test/check_engine.js
 *
 * 1. Text: the same paragraphs, headings, sentences, tokens and spans, names and story start.
 * 2. Words: how often the browser's lemma table gives the dictionary form Python's lemmatizer gives.
 * 3. Course: given Python's dictionary forms, exactly the same course (words learned, sessions,
 *    study lists in order, glosses) and the same examples, from zero and knowing 1,000 words.
 * 4. Ranking: the general frequency ranking of the book's words.
 * Exits non-zero if any exact check fails.
 */
const fs = require("fs");
const path = require("path");
const R = require("../engine.js");

const HERE = __dirname, APP = path.join(HERE, "..");
const BOOKS = {marianela: "es-marianela.txt", candide: "fr-candide.txt", verwandlung: "de-die-verwandlung.txt", alice: "en-alice.txt"};
let failed = 0;
const fail = (msg) => { failed++; console.log("  FAIL " + msg); };
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

for (const [name, file] of Object.entries(BOOKS)) {
  const ref = JSON.parse(fs.readFileSync(path.join(HERE, `ref-${name}.json`), "utf8"));
  const Lg = R.loadLanguage(JSON.parse(fs.readFileSync(path.join(APP, "data", `${ref.lang}.json`), "utf8")));
  const text = fs.readFileSync(path.join(APP, "..", "books", file), "utf8");
  const t0 = Date.now();
  const doc = R.analyze(R.paragraphsFromText(text), Lg);
  const ms = Date.now() - t0;
  console.log(`== ${name} (${ref.lang}), analysed in ${ms} ms`);

  // 1. text structure
  let structDiff = 0, firstDiff = null;
  if (doc.paragraphs.length !== ref.paragraphs.length) fail(`${doc.paragraphs.length} paragraphs, Python ${ref.paragraphs.length}`);
  ref.paragraphs.forEach((rp, i) => {
    const jp = doc.paragraphs[i];
    const a = jp && [jp.heading, jp.sentences.map(s => [s.text, s.tokens.map(t => [t.text, t.start, t.end])])];
    const b = [rp.heading, rp.sentences.map(s => [s.text, s.tokens.map(t => [t[0], t[1], t[2]])])];
    if (!same(a, b)) { structDiff++; if (!firstDiff) firstDiff = {i, js: JSON.stringify(a).slice(0, 300), py: JSON.stringify(b).slice(0, 300)}; }
  });
  if (structDiff) { fail(`${structDiff} paragraphs differ in structure`); console.log(firstDiff); }
  if (doc.start !== ref.start) fail(`story starts at ${doc.start}, Python ${ref.start}`);
  if (!same([...doc.names].sort(), ref.names.slice().sort())) fail(`names differ: ${doc.names.size} vs ${ref.names.length}`);

  // 2. dictionary forms
  let n = 0, agree = 0;
  const diff = new Map();
  ref.paragraphs.forEach((rp, i) => rp.sentences.forEach((rs, j) => rs.tokens.forEach((rt, k) => {
    const jt = doc.paragraphs[i]?.sentences[j]?.tokens[k];
    if (!jt || rt[3] === null) return;
    n++;
    if (jt.key === rt[3] && same(jt.extra, rt[4])) agree++;
    else { const key = `${rt[0]}: ${rt[3]}${rt[4].length ? "+" + rt[4].join("+") : ""} / js ${jt.key}${jt.extra.length ? "+" + jt.extra.join("+") : ""}`; diff.set(key, (diff.get(key) || 0) + 1); }
  })));
  console.log(`  dictionary forms: ${agree}/${n} tokens agree with Python (${(100 * agree / n).toFixed(2)}%); most common differences:`,
              [...diff].sort((a, b) => b[1] - a[1]).slice(0, 6).map(([k, v]) => `${k} ×${v}`).join("; "));

  // 3. course, from Python's dictionary forms
  const pdoc = {lang: ref.lang, start: ref.start, names: new Set(ref.names), paragraphs: ref.paragraphs.map(p => ({
    heading: p.heading, sentences: p.sentences.map(s => ({text: s.text, tokens: s.tokens.map(t => ({text: t[0], start: t[1], end: t[2], key: t[3], extra: t[4]}))}))}))};
  for (const [label, rc] of Object.entries(ref.courses)) {
    const c = R.buildCourse(pdoc, new Set(rc.known), {cap: 2, learnCost: 6, daily: 15});
    const st = R.courseStats(c);
    if (!same([...c.learned].sort(), rc.learned.slice().sort())) fail(`${label}: learned sets differ (${c.learned.size} vs ${rc.learned.length})`);
    let sdiff = 0;
    rc.sessions.forEach((rs, i) => {
      const js = c.sessions[i];
      const a = js && [js.title, js.paragraphs, js.tokens, js.learn, Object.fromEntries([...js.glossed].sort((x, y) => (x[0] < y[0] ? -1 : 1))), js.sentences, js.sentencesGlossed];
      const b = [rs.title, rs.paragraphs, rs.tokens, rs.learn, rs.glossed, rs.sentences, rs.sentences_glossed];
      if (!same(a, b)) { sdiff++; if (sdiff === 1) console.log("   first differing session", i, JSON.stringify(a).slice(0, 400), "\n   python", JSON.stringify(b).slice(0, 400)); }
    });
    if (c.sessions.length !== rc.sessions.length || sdiff) fail(`${label}: ${sdiff} of ${rc.sessions.length} sessions differ`);
    const ps = rc.stats;
    if (st.taught !== ps.taught || st.days !== ps.days || st.startDay !== ps.start_day || Math.abs(st.glossesPerPage - ps.glosses_per_page) > 0.006)
      fail(`${label}: stats ${JSON.stringify(st)} vs ${JSON.stringify(ps)}`);
    const tr = R.tradeoff(pdoc, new Set(rc.known));
    if (!same(tr.map(t => [t.cap, t.taught, t.glosses, t.tokens]), rc.tradeoff.map(t => [t.cap, t.taught, t.glosses, t.tokens]))) fail(`${label}: trade-off differs`);
    // examples, and meanings
    const data = R.packData(pdoc, c, Lg);
    const ex = data.sessions.map(s => s.learn.map(([id, html, left]) => [data.words[id][0], html, left]));
    let exDiff = 0, exN = 0;
    rc.examples.forEach((rs, i) => rs.forEach((e, k) => { exN++; if (!same(ex[i] && ex[i][k], e)) { exDiff++; if (exDiff === 1) console.log("   first differing example", JSON.stringify(ex[i] && ex[i][k]), JSON.stringify(e)); } }));
    if (exDiff) fail(`${label}: ${exDiff}/${exN} examples differ`);
    const pyGloss = new Map(rc.words.map(w => [w[0], w[2]]));
    let gN = 0, gSame = 0, gMissing = 0;
    for (const w of data.words) { if (!pyGloss.has(w[0])) continue; gN++; if (pyGloss.get(w[0]) === w[2]) gSame++; else if (!w[2] && pyGloss.get(w[0])) gMissing++; }
    console.log(`  course ${label}: ${st.sessions} sessions, learn ${st.taught}, ${st.glossesPerPage.toFixed(2)} glosses a page, `
                + `first page day ${st.startDay}, ${exN} examples; meanings same as Python for ${gSame}/${gN} words (${gMissing} missing in the browser data)`);
  }

  // 4. general ranking, with Python's dictionary forms
  const lemmas = [...new Set(ref.paragraphs.flatMap(p => p.sentences.flatMap(s => s.tokens.map(t => t[3]).filter(k => k !== null))))].sort();
  const ranked = R.rankedLemmas(Lg, lemmas).slice(0, 3000);
  let k = 0;
  while (k < ranked.length && ranked[k] === ref.ranked[k]) k++;
  const top = new Set(ranked.slice(0, 1000)), ptop = new Set(ref.ranked.slice(0, 1000));
  const overlap = [...top].filter(x => ptop.has(x)).length;
  console.log(`  general ranking: identical for the first ${k} entries; top 1,000 overlap ${overlap}`);
  if (k < 1000) fail(`ranking differs at ${k}: ${JSON.stringify(ranked[k])} vs ${JSON.stringify(ref.ranked[k])}`);

  // the course from the browser's own dictionary forms
  const c2 = R.buildCourse(doc, new Set(), {cap: 2, learnCost: 6, daily: 15});
  const s2 = R.courseStats(c2), p2 = ref.courses.zero.stats;
  console.log(`  course from zero with the browser's forms: learn ${s2.taught} (Python ${p2.taught}), ${s2.sessions} sessions, `
              + `${s2.glossesPerPage.toFixed(2)} glosses a page (Python ${p2.glosses_per_page})`);
}
console.log(failed ? `\n${failed} check(s) failed` : "\nall exact checks pass");
process.exit(failed ? 1 : 0);
