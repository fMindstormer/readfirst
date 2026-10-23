/* Readfirst engine, in the browser and in Node: from a book to a course.
 *
 * A port of the Python package (readfirst/text.py, course.py, pack.py), checked against it by
 * app/test/check_engine.mjs. One difference: words to learn are chosen with the rule (learn every
 * word met `learnCost` times or more, then the most frequent word of any sentence that still needs
 * too many glosses) instead of the integer program, which costs 0-1.2% more words on the books
 * measured.
 */
(function (root) {
  "use strict";

  // ---------------------------------------------------------------- characters
  const L = "[\\p{L}\\p{Nl}\\p{No}]";                       // Python's [^\W\d_]
  const TOKEN = new RegExp(`${L}+(?:['’]${L}+)*`, "gu");
  const OPENERS = "¿¡«“\"'(—–-‘";
  const CLOSERS = "\"'»”’)]";
  const cls = s => "[" + [...s].map(c => ("\\]^-[".includes(c) ? "\\" + c : c)).join("") + "]";
  const SPLIT = new RegExp(`(?<=[.!?…])(${cls(CLOSERS)}*)\\s+(?=${cls(OPENERS)}*${L}(?<=[A-ZÀ-ÖØ-Þ]))`, "gu");
  const ABBREV = new Set(["mr", "mrs", "ms", "dr", "st", "sr", "sra", "srta", "dña", "d", "mme", "mlle", "m", "hr",
    "fr", "nr", "etc", "vs", "jr", "prof", "gen", "capt", "col", "lt", "rev", "hon", "z.b", "u.s", "no"]);
  const ELISION_FR = {l: "le", d: "de", j: "je", qu: "que", n: "ne", s: "se", c: "ce", m: "me", t: "te",
    jusqu: "jusque", lorsqu: "lorsque", puisqu: "puisque", quoiqu: "quoique", presqu: "presque"};
  const NOT_NAMES = new Set(["I", "I'm", "I'll", "I've", "I'd", "OK", "O"]);
  const NOUN_CAPS = new Set(["de"]);
  const KEEP = {
    es: new Set("yo me mí conmigo tú te ti contigo usted ustedes él ella ello lo la le se sí consigo nosotros nosotras nos vosotros vosotras os ellos ellas los las les".split(" ")),
    fr: new Set("je me moi tu te toi il elle on le la lui se soi nous vous ils elles les leur eux en y".split(" ")),
    de: new Set("ich mich mir du dich dir er ihn ihm sie es sich wir uns ihr euch ihnen".split(" ")),
    en: new Set("i me you he him she her it we us they them".split(" ")),
  };
  const HEAD_WORD = /^(chapter|chapitre|cap[ií]tulo|kapitel|book|part|libro|parte|livre|teil|tome|acte?)(?![\p{L}\p{N}_])/iu;
  const CHAPTER_WORD = /^(chapter|chapitre|cap[ií]tulo|kapitel)(?![\p{L}\p{N}_])/iu;
  const ROMAN = /^([IVXLC]+)\.?(?:\s+(.*))?$/u;
  const CLITICS_ES = ["nos", "les", "los", "las", "me", "te", "se", "lo", "la", "le", "os"];
  const VERB_ES = /(ar|er|ir|ír|ando|iendo|yendo)$/u;

  // Python's str.islower / str.isupper: by the Unicode Lowercase and Uppercase properties
  const isLower = c => /\p{Lowercase}/u.test(c);
  const isUpperChar = c => /\p{Uppercase}/u.test(c);
  const isUpperStr = s => /\p{Uppercase}/u.test(s) && !/[\p{Lowercase}\p{Lt}]/u.test(s);
  const capitalize = s => { const a = [...s]; return a.length ? a[0].toUpperCase() + a.slice(1).join("").toLowerCase() : s; };
  const first = s => [...s][0] || "";
  const cmpStr = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
  const pyStrip = s => s.replace(/^\s+|\s+$/gu, "");

  const HORIZON = 60;                                      // pages introducer looks ahead in a large book
  const EXACT_ARCS = 10000;                                // word-page pairs up to which it plans the whole book

  // ------------------------------------------------------------- language data
  /** Language data as exported by app/build_data.py. */
  function loadLanguage(data) {
    const forms = new Map();
    for (const line of data.lemmas.split("\n")) {
      const tab = line.indexOf("\t");
      if (tab < 0) continue;
      const lemma = line.slice(0, tab);
      for (const code of line.slice(tab + 1).split("|")) {
        const k = parseInt(code[0], 36);
        forms.set(lemma.slice(0, k) + code.slice(1), lemma);
      }
    }
    const known = new Set(data.known ? data.known.split("\n") : []);
    const ruled = new Set(data.ruled ? data.ruled.split("\n") : []);
    return {lang: data.lang, forms, known, ruled, freq: data.freq ? data.freq.split("\n") : [], gloss: data.gloss || {},
            source: data.source || "", overrides: {}};
  }

  function lemmaOf(L, w) {
    const r = L.forms.get(w);
    return r === undefined ? w : r;
  }
  // simplemma.is_known: in its dictionary (forms it lemmatizes by rule are not)
  const isKnown = (L, w) => (L.forms.has(w) && !L.ruled.has(w)) || L.known.has(w);

  function splitClitics(L, word) {
    let w = word.toLowerCase();
    if (isKnown(L, w)) return null;
    const found = [];
    for (let round = 0; round < 2; round++) {
      let hit = false;
      for (const c of CLITICS_ES) {
        if (w.endsWith(c) && w.length - c.length >= 3) {
          const stem = w.slice(0, -c.length).replace(/[áéíóú]/g, ch => "aeiou"["áéíóú".indexOf(ch)]);
          found.unshift(c);
          w = w.slice(0, -c.length);
          if (VERB_ES.test(stem) && isKnown(L, stem)) return [stem, found.slice()];
          hit = true;
          break;
        }
      }
      if (!hit) break;
    }
    return null;
  }

  // ------------------------------------------------------------------- text
  function stripGutenberg(text) {
    let m = /\*\*\*\s*START OF (THE|THIS) PROJECT GUTENBERG[^\n]*\n/.exec(text);
    if (m) text = text.slice(m.index + m[0].length);
    m = /\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG|^End of (the )?Project Gutenberg/m.exec(text);
    if (m) text = text.slice(0, m.index);
    return text;
  }

  function splitParagraph(para) {
    const out = [];
    if (para) {
      let start = 0;
      SPLIT.lastIndex = 0;
      let m;
      while ((m = SPLIT.exec(para)) !== null) {
        if (m[0].length === 0) { SPLIT.lastIndex++; continue; }
        const before = para.slice(start, m.index);
        const last = /([\p{L}\p{N}_]+)\.$/u.exec(before);
        if (last && (ABBREV.has(last[1].toLowerCase()) || ([...last[1]].length === 1 && isUpperStr(last[1])))) continue;
        out.push(pyStrip(para.slice(start, m.index + m[1].length)));
        start = m.index + m[0].length;
      }
      out.push(pyStrip(para.slice(start)));
    }
    return out.filter(s => s);
  }

  /** Tokens with their spans (in UTF-16 units of the sentence); French elisions split after the apostrophe. */
  function tokenSpans(sentence, lang) {
    const out = [];
    TOKEN.lastIndex = 0;
    let m;
    while ((m = TOKEN.exec(sentence)) !== null) {
      let t = m[0].replace(/’/g, "'"), a = m.index;
      if ((lang === "fr" || lang === "it" || lang === "ca") && t.includes("'")) {
        while (t.includes("'")) {
          const i = t.indexOf("'");
          const head = t.slice(0, i);
          out.push([head + "'", a, a + head.length + 1]);
          a += head.length + 1;
          t = t.slice(i + 1);
        }
        if (t) out.push([t, a, a + t.length]);
      } else {
        out.push([t, a, m.index + m[0].length]);
      }
    }
    return out;
  }

  function isHeading(par) {
    const words = par.match(TOKEN) || [];
    const lastCh = par.slice(-1);
    if (!par || "?!\"»”".includes(lastCh) || words.length > (HEAD_WORD.test(par) ? 25 : 12)) return false;
    if (HEAD_WORD.test(par)) return true;
    const m = ROMAN.exec(par);
    if (!m) return false;
    const rest = m[2];
    if (!rest) return true;
    const firstRest = rest.split(/\s+/).filter(Boolean)[0] || "";
    return !isLower(first(rest)) && !(m[1].length === 1 && isLower(first(firstRest)));
  }

  /** Paragraphs from plain text: blank lines separate paragraphs; short "Chapter ..." lines are headings. */
  function paragraphsFromText(text) {
    text = stripGutenberg(text.normalize("NFC"));
    const out = [];
    for (const block of text.split(/\n\s*\n/)) {
      const flat = pyStrip(block.replace(/\s+/gu, " "));
      if (!flat) continue;
      const lines = (pyStrip(block).match(/\n/g) || []).length + 1;
      const head = isHeading(flat) && (lines === 1 || (lines <= 3 && HEAD_WORD.test(flat)));
      out.push({text: flat, heading: head});
    }
    return out;
  }

  /** The book in reading order, every token with its dictionary form (null for a name). */
  function analyze(paras, Lg, opts = {}) {
    const lang = Lg.lang;
    const raw = paras.map(p => ({text: p.text, heading: p.heading,
      sents: splitParagraph(p.text).map(s => [s, tokenSpans(s, lang)])}));
    const lowerSeen = new Set(), capMid = new Set();
    for (const p of raw) for (const [, spans] of p.sents) spans.forEach(([t], i) => {
      if (isLower(first(t))) lowerSeen.add(t.toLowerCase());
      else if (i > 0) capMid.add(t);
    });
    const names = opts.names === undefined ? !NOUN_CAPS.has(lang) : opts.names;
    const nameSet = new Set();
    if (names) for (const t of capMid) {
      if (!lowerSeen.has(t.toLowerCase()) && [...t].length > 1 && !NOT_NAMES.has(t) && !isUpperStr(t)) nameSet.add(t);
    }
    const keep = KEEP[lang] || new Set();
    const cache = new Map();
    const key = (t, initial) => {
      const ck = t + "\u0001" + (initial ? 1 : 0);
      if (cache.has(ck)) return cache.get(ck);
      let r;
      if (keep.has(t.toLowerCase())) r = t.toLowerCase();
      else if ((lang === "fr" || lang === "it" || lang === "ca") && t.endsWith("'")) {
        const h = t.slice(0, -1).toLowerCase();
        r = lang === "fr" ? (ELISION_FR[h] || h) : lemmaOf(Lg, h);
      } else if (NOUN_CAPS.has(lang)) {
        let w = t;
        if (isUpperStr(t) && [...t].length > 1) w = capitalize(t);
        if (initial && isUpperChar(first(t)) && lowerSeen.has(t.toLowerCase()) && !capMid.has(t)) w = t.toLowerCase();
        r = lemmaOf(Lg, w);
        if (!isUpperChar(first(w))) r = r.toLowerCase();
      } else {
        r = lemmaOf(Lg, t.toLowerCase()).toLowerCase();
      }
      cache.set(ck, r);
      return r;
    };
    const paragraphs = raw.map(p => ({heading: p.heading, sentences: p.sents.map(([s, spans]) => ({
      text: s,
      tokens: spans.map(([t, a, b], i) => {
        if (nameSet.has(t)) return {text: t, start: a, end: b, key: null, extra: []};
        const split = lang === "es" ? splitClitics(Lg, t) : null;
        if (split) return {text: t, start: a, end: b, key: key(split[0], false), extra: split[1]};
        return {text: t, start: a, end: b, key: key(t, i === 0), extra: []};
      }),
    }))}));
    return {lang, paragraphs, start: mainStart(paragraphs), names: nameSet};
  }

  function narrative(p) {
    const toks = [];
    for (const s of p.sentences) for (const t of s.tokens) toks.push(t.text);
    return !p.heading && toks.length >= 40 && toks.filter(t => isLower(first(t))).length >= 0.6 * toks.length;
  }

  function mainStart(pars) {
    const followed = i => {
      for (let q = i + 1; q < pars.length; q++) {
        if (pars[q].heading) return false;
        if (narrative(pars[q])) return true;
      }
      return false;
    };
    const texts = pars.map(p => p.sentences.map(s => s.text).join(" "));
    for (const pick of [i => CHAPTER_WORD.test(texts[i]), () => true]) {
      for (let i = 0; i < pars.length; i++) if (pars[i].heading && pick(i) && followed(i)) return i;
    }
    const i = pars.findIndex(narrative);
    return i < 0 ? 0 : i;
  }

  // ----------------------------------------------------------------- course
  function sessionsOf(doc, target = 1000, minSize = 200, firstSize = 250) {
    const out = [], pars = doc.paragraphs;
    let start = doc.start, size = 0, title = "", chapter = "";
    const close = end => {
      if (end > start) out.push({index: out.length, title, paragraphs: [start, end], tokens: size,
                                 learn: [], glossed: new Map(), sentences: 0, sentencesGlossed: 0});
      start = end; size = 0;
    };
    for (let i = doc.start; i < pars.length; i++) {
      const p = pars[i];
      if (p.heading) {
        if (size >= minSize) close(i);
        chapter = p.sentences.map(s => s.text).join(" ");
        if (size === 0) title = chapter;
        continue;
      }
      if (size === 0 && !title) title = chapter;
      for (const s of p.sentences) size += s.tokens.length;
      if (size >= Math.min(target, firstSize * (out.length + 1))) {
        close(i + 1);
        title = chapter ? chapter + " (cont.)" : "";
      }
    }
    close(pars.length);
    out.forEach((s, k) => { if (!s.title) s.title = `Part ${k + 1}`; });
    return out;
  }

  function wordsOf(ds) {
    const out = [];
    for (const t of ds.tokens) if (t.key !== null) { out.push(t.key); for (const x of t.extra) out.push(x); }
    return out;
  }

  function storyUnits(doc, known) {
    const units = [], occ = new Map();
    for (const p of doc.paragraphs.slice(doc.start)) for (const ds of p.sentences) {
      const ws = wordsOf(ds).filter(w => !known.has(w));
      units.push(new Set(ws));
      for (const w of ws) occ.set(w, (occ.get(w) || 0) + 1);
    }
    return {units, occ};
  }

  function rentOrBuyRule(units, occ, learnCost = 6, cap = 2) {
    const learned = new Set();
    for (const [w, n] of occ) if (n >= learnCost) learned.add(w);
    for (const u of units) {
      const rest = [...u].filter(w => !learned.has(w)).sort((a, b) => (occ.get(b) - occ.get(a)) || cmpStr(a, b));
      while (rest.length > cap) learned.add(rest.shift());
    }
    return learned;
  }

  // min-heap of [negScore, negFreq, index] in Python tuple order
  function heapPush(h, x) {
    h.push(x);
    let i = h.length - 1;
    while (i > 0) {
      const p = (i - 1) >> 1;
      if (lessT(h[i], h[p])) { [h[i], h[p]] = [h[p], h[i]]; i = p; } else break;
    }
  }
  function heapPop(h) {
    const top = h[0], last = h.pop();
    if (h.length) {
      h[0] = last;
      let i = 0;
      for (;;) {
        const l = 2 * i + 1, r = l + 1;
        let m = i;
        if (l < h.length && lessT(h[l], h[m])) m = l;
        if (r < h.length && lessT(h[r], h[m])) m = r;
        if (m === i) break;
        [h[i], h[m]] = [h[m], h[i]]; i = m;
      }
    }
    return top;
  }
  const lessT = (a, b) => a[0] !== b[0] ? a[0] < b[0] : a[1] !== b[1] ? a[1] < b[1] : a[2] < b[2];

  /** The plan's greedy (readfirst/order.py): learn the word that makes the most sentences readable
   * now, with a little credit for sentences it brings to one or two missing words. */
  function greedy(words, edges, freq, credit = [0.0, 1.0, 0.05, 0.002]) {
    const n = words.length;
    const ofWord = Array.from({length: n}, () => []);
    edges.forEach((e, j) => { for (const w of e) ofWord[w].push(j); });
    const miss = edges.map(e => e.length);
    const f = m => (m < credit.length ? credit[m] : 0.0);
    const score = new Array(n).fill(0.0);
    edges.forEach(e => { const v = f(e.length); if (v) for (const w of e) score[w] += v; });
    const known = new Array(n).fill(false), current = new Set(Array.from({length: n}, (_, i) => i));
    const heap = [];
    for (let w = 0; w < n; w++) heapPush(heap, [-score[w], -freq[w], w]);
    const order = [];
    while (current.size) {
      const [s, , w] = heapPop(heap);
      if (known[w] || -s !== score[w]) continue;
      known[w] = true; current.delete(w); order.push(w);
      for (const j of ofWord[w]) {
        const old = miss[j]; miss[j] -= 1;
        const d = f(miss[j]) - f(old);
        if (d) for (const u of edges[j]) if (!known[u]) {
          score[u] += d;
          if (current.has(u)) heapPush(heap, [-score[u], -freq[u], u]);
        }
      }
    }
    return order;
  }

  function unlockOrder(units, chosen, occ) {
    if (!chosen.size) return [];
    const sets = [];
    for (const u of units) { const s = [...u].filter(w => chosen.has(w)); if (s.length) sets.push(s); }
    const words = [...new Set(sets.flat())].sort(cmpStr);
    const index = new Map(words.map((w, i) => [w, i]));
    const edges = sets.map(s => s.map(w => index.get(w)).sort((a, b) => a - b));
    const order = greedy(words, edges, words.map(w => occ.get(w) || 0)).map(i => words[i]);
    const inOrder = new Set(order);
    const rest = [...chosen].filter(w => !inOrder.has(w)).sort((a, b) => ((occ.get(b) || 0) - (occ.get(a) || 0)) || cmpStr(a, b));
    return order.concat(rest);
  }

  function buildCourse(doc, known, {cap = 2, learnCost = 6, daily = 15, sessions = null} = {}) {
    known = new Set(known);
    const {units, occ} = storyUnits(doc, known);
    const learned = rentOrBuyRule(units, occ, learnCost, cap);
    sessions = sessions || sessionsOf(doc);
    const seen = new Set(known);
    for (const s of sessions) {
      const sUnits = [];
      for (let i = s.paragraphs[0]; i < s.paragraphs[1]; i++) for (const ds of doc.paragraphs[i].sentences) {
        const ws = wordsOf(ds);
        sUnits.push(new Set(ws.filter(w => !known.has(w))));
        let hit = false;
        for (const w of ws) if (!known.has(w) && !learned.has(w)) { s.glossed.set(w, (s.glossed.get(w) || 0) + 1); hit = true; }
        s.sentences += 1;
        s.sentencesGlossed += hit ? 1 : 0;
      }
      const nw = new Set();
      for (const u of sUnits) for (const w of u) if (learned.has(w) && !seen.has(w)) nw.add(w);
      s.learn = unlockOrder(sUnits, nw, occ);
      for (const w of nw) seen.add(w);
    }
    return {lang: doc.lang, known, sessions, learned, daily, cap, learnCost};
  }

  function courseStats(c) {
    const tok = c.sessions.reduce((a, s) => a + s.tokens, 0);
    let g = 0;
    for (const s of c.sessions) for (const v of s.glossed.values()) g += v;
    const days = c.sessions.reduce((a, s) => a + Math.max(1, Math.ceil(s.learn.length / c.daily)), 0);
    return {sessions: c.sessions.length, taught: c.learned.size, days,
            startDay: c.sessions.length ? Math.max(1, Math.ceil(c.sessions[0].learn.length / c.daily)) : 0,
            glosses: g, glossesPerPage: 250 * g / Math.max(1, tok), coverage: 1 - g / Math.max(1, tok), tokens: tok,
            sentencesWithGloss: c.sessions.reduce((a, s) => a + s.sentencesGlossed, 0) /
                                Math.max(1, c.sessions.reduce((a, s) => a + s.sentences, 0))};
  }

  /** Words to learn against glosses per page, for each comfort level. */
  function tradeoff(doc, known, learnCost = 6) {
    const {units, occ} = storyUnits(doc, new Set(known));
    let tok = 0;
    for (const p of doc.paragraphs.slice(doc.start)) for (const s of p.sentences) tok += s.tokens.length;
    return [1, 2, 3].map(cap => {
      const learned = rentOrBuyRule(units, occ, learnCost, cap);
      let g = 0;
      for (const [w, n] of occ) if (!learned.has(w)) g += n;
      return {cap, taught: learned.size, glosses: g, tokens: tok, glossesPerPage: 250 * g / Math.max(1, tok),
              coverage: 1 - g / Math.max(1, tok)};
    });
  }

  // ---------------------------------------------------------- general frequency
  /** The book's words in the order a general frequency list reaches them (readfirst/general.py);
   * list words the book never uses are kept as placeholders starting with "\0". */
  function rankedLemmas(Lg, bookLemmas) {
    const lower = new Map();
    for (const k of bookLemmas) { const l = k.toLowerCase(); if (!lower.has(l)) lower.set(l, []); lower.get(l).push(k); }
    const keep = KEEP[Lg.lang] || new Set();
    const out = [], seen = new Set();
    for (const w of Lg.freq) {
      let cands;
      if (keep.has(w)) cands = [w];
      else {
        cands = [lemmaOf(Lg, w).toLowerCase(), w];
        if (Lg.lang === "de") cands.unshift(lemmaOf(Lg, capitalize(w)).toLowerCase());
      }
      let keys = null;
      for (const c of cands) if (lower.has(c)) { keys = lower.get(c); break; }
      if (!keys) keys = ["\0" + cands[0]];
      for (const k of keys) if (!seen.has(k)) { seen.add(k); out.push(k); }
    }
    return out;
  }

  /** A word typed or pasted by the learner, as the book's dictionary forms it could be. */
  function knownKeys(Lg, word, bookLemmas) {
    const w = word.trim();
    if (!w) return [];
    const c = new Set([w, w.toLowerCase(), lemmaOf(Lg, w).toLowerCase(), lemmaOf(Lg, w.toLowerCase()).toLowerCase(),
                       lemmaOf(Lg, w), capitalize(w), lemmaOf(Lg, capitalize(w))]);
    return [...c].filter(k => bookLemmas.has(k));
  }

  // ------------------------------------------------------------------ glosses
  function shortGloss(g, limit = 24) {
    let f = g ? pyStrip(g.split(/;\s|,\s/u)[0]) : "";
    f = f.replace(/\s*\((der|die|das)\)$/u, "");
    return [...f].length <= limit ? f : pyStrip([...f].slice(0, limit - 1).join("")) + "…";
  }
  function glossOf(Lg, lemma, forms = []) {
    for (const k of [lemma, lemma.toLowerCase(), ...forms, ...forms.map(f => f.toLowerCase())]) {
      if (Object.prototype.hasOwnProperty.call(Lg.gloss, k)) return Lg.gloss[k];
    }
    return "";
  }
  const escHtml = s => String(s).replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#x27;"}[c]));

  function mark(text, spans, ids) {
    const out = [];
    let at = 0;
    for (const [a, b, wid] of spans.slice().sort((x, y) => x[0] - y[0] || x[1] - y[1] || cmpStr(String(x[2]), String(y[2])))) {
      if (ids.has(wid)) { out.push(escHtml(text.slice(at, a))); out.push("<b>" + escHtml(text.slice(a, b)) + "</b>"); at = b; }
    }
    out.push(escHtml(text.slice(at)));
    return out.join("");
  }

  /** Everything the reader shows: each session's study list with an example from its pages, and
   * its pages with every word to gloss marked (pack.py's pack_data). With `all`, words already
   * learned or known are marked too (kind 3), so the reader can show any word's meaning on tap. */
  function packData(doc, course, Lg, {all = false} = {}) {
    const forms = new Map();
    for (const p of doc.paragraphs.slice(doc.start)) for (const ds of p.sentences) for (const t of ds.tokens) {
      if (t.key === null) continue;
      if (!forms.has(t.key)) forms.set(t.key, new Map());
      const m = forms.get(t.key);
      m.set(t.text, (m.get(t.text) || 0) + 1);
    }
    const ids = new Map(), words = [];
    const wid = w => {
      if (!ids.has(w)) {
        const f = forms.has(w) ? [...forms.get(w)].map((e, i) => [e[0], e[1], i]).sort((a, b) => b[1] - a[1] || a[2] - b[2]).slice(0, 3) : [];
        const g = glossOf(Lg, w, f.map(x => x[0]));
        ids.set(w, words.length);
        words.push([w, f.length ? f[0][0] : w, g, shortGloss(g)]);
      }
      return ids.get(w);
    };
    const known = course.known, learnedBefore = new Set(known);
    const sessions = [];
    for (const s of course.sessions) {
      const nw = new Set(s.learn);
      const paras = [], sentList = [];
      for (let i = s.paragraphs[0]; i < s.paragraphs[1]; i++) {
        const ps = [];
        for (const ds of doc.paragraphs[i].sentences) {
          const spans = [];
          for (const t of ds.tokens) {
            if (t.key === null) continue;
            const ws = [t.key, ...t.extra];
            const n1 = ws.find(w => nw.has(w));
            if (n1 !== undefined) spans.push([t.start, t.end, 1, wid(n1)]);
            else {
              const n2 = ws.find(w => !course.learned.has(w) && !known.has(w));
              if (n2 !== undefined) spans.push([t.start, t.end, 2, wid(n2)]);
              else if (all) spans.push([t.start, t.end, 3, wid(t.key)]);
            }
          }
          ps.push([ds.text, spans]);
          sentList.push([ds, new Set(wordsOf(ds).filter(w => !known.has(w)))]);
        }
        paras.push(ps);
      }
      const have = new Set(learnedBefore), gl = new Set(s.glossed.keys());
      const learn = [];
      const left = u => { let n = 0; for (const x of u) if (!have.has(x) && !gl.has(x)) n++; return n; };
      for (const w of s.learn) {
        const before = sentList.filter(([, u]) => {
          if (!u.has(w)) return false;
          for (const x of u) if (x !== w && !have.has(x) && !gl.has(x)) return false;
          return true;
        });
        have.add(w);
        let ds, lft;
        if (before.length) {
          ds = before.reduce((a, b) => (b[0].text.length < a[0].text.length ? b : a))[0]; lft = 0;
        } else {
          const cands = sentList.filter(([, u]) => u.has(w));
          const best = cands.reduce((a, b) => {
            const la = left(a[1]), lb = left(b[1]);
            return lb < la || (lb === la && b[0].text.length < a[0].text.length) ? b : a;
          });
          ds = best[0]; lft = left(best[1]);
        }
        const spans = ds.tokens.filter(t => t.key !== null && (t.key === w || t.extra.includes(w))).map(t => [t.start, t.end, w]);
        learn.push([wid(w), mark(ds.text, spans, new Set([w])), lft]);
      }
      for (const w of nw) learnedBefore.add(w);
      let glosses = 0;
      for (const v of s.glossed.values()) glosses += v;
      sessions.push({title: s.title, learn, paras, tokens: s.tokens, glosses});
    }
    return {lang: doc.lang, words, sessions, source: Lg.source};
  }

  // ------------------------------------------------------- pages for reading
  const sentenceTokens = s => s.tokens.length;

  /** Screen-sized pages of the story, about `size` words each. A page ends at a paragraph break,
   * or at a sentence break inside a long paragraph; a chapter heading starts a new page. A page is
   * {pieces: [[paragraph, first sentence, end sentence], ...], tokens, chapter}. */
  function pagesOf(doc, size = 220) {
    const pages = [], pars = doc.paragraphs;
    let cur = null, chapter = "";
    const open = () => { cur = {pieces: [], tokens: 0, chapter}; pages.push(cur); };
    for (let i = doc.start; i < pars.length; i++) {
      const p = pars[i], n = p.sentences.length;
      const total = p.sentences.reduce((a, s) => a + sentenceTokens(s), 0);
      if (p.heading) {
        chapter = p.sentences.map(s => s.text).join(" ");
        if (!cur || cur.tokens >= 0.3 * size) open();
        cur.chapter = chapter;
        cur.pieces.push([i, 0, n]); cur.tokens += total;
        continue;
      }
      if (!cur) open();
      if (total <= 1.6 * size) {
        if (cur.tokens > 0.5 * size && cur.tokens + total > 1.6 * size) open();
        cur.pieces.push([i, 0, n]); cur.tokens += total;
        if (cur.tokens >= size) cur = null;
        continue;
      }
      let a = 0;                                   // a long paragraph: cut between sentences
      for (let k = 0; k < n; k++) {
        cur.tokens += sentenceTokens(p.sentences[k]);
        if (cur.tokens >= size && k + 1 < n) { cur.pieces.push([i, a, k + 1]); a = k + 1; open(); }
      }
      cur.pieces.push([i, a, n]);
      if (cur.tokens >= size) cur = null;
    }
    return pages;
  }

  function* pageSentences(doc, page) {
    for (const [pi, a, b] of page.pieces) for (let k = a; k < b; k++) yield doc.paragraphs[pi].sentences[k];
  }

  /** The words a page introduces: words worth learning met on it that the reader does not know and
   * has not met as new words before, at most `perPage`, preferring those the rest of the book uses
   * most (`occ`: occurrences from this page on); in reading order. */
  function introductionsOn(doc, page, learned, isDone, perPage, occ) {
    const cands = [], seen = new Set();
    for (const s of pageSentences(doc, page)) for (const w of wordsOf(s)) {
      if (learned.has(w) && !isDone(w) && !seen.has(w)) { seen.add(w); cands.push(w); }
    }
    const pick = new Set(cands.slice().sort((x, y) => ((occ.get(y) || 0) - (occ.get(x) || 0)) || cmpStr(x, y)).slice(0, perPage));
    return cands.filter(w => pick.has(w));
  }

  /** Words to pages, exactly: `gains[i]` lists [page, gain] for word i, the pages it may go to; each
   * word goes to at most one page, each page takes at most `cap` words, and the total gain is the
   * largest possible (`cap` a number, or one per page). A min-cost flow (source -> word -> page ->
   * sink), primal-dual: Dijkstra with
   * potentials finds the cheapest augmenting cost, then a blocking flow (Dinic) on the arcs of
   * reduced cost 0 takes every path of that cost; it stops when a path would gain nothing. Returns
   * each word's page, or -1. */
  function assignPages(gains, nPages, cap) {
    const n = gains.length, S = n + nPages, T = S + 1, V = T + 1;
    const E = 2 * (n + nPages + gains.reduce((a, g) => a + g.length, 0));
    const head = new Int32Array(V).fill(-1), to = new Int32Array(E), next = new Int32Array(E), res = new Int32Array(E), cost = new Float64Array(E);
    let m = 0;
    const arc = (a, b, c, w) => {
      to[m] = b; res[m] = c; cost[m] = w; next[m] = head[a]; head[a] = m++;
      to[m] = a; res[m] = 0; cost[m] = -w; next[m] = head[b]; head[b] = m++;
      return m - 2;
    };
    const pot = new Float64Array(V), wordArcs = gains.map(() => []);
    for (let p = 0; p < nPages; p++) arc(n + p, T, typeof cap === "number" ? cap : cap[p], 0);
    gains.forEach((g, i) => {
      arc(S, i, 1, 0);
      for (const [p, gain] of g) { wordArcs[i].push([arc(i, n + p, 1, -gain), p]); pot[n + p] = Math.min(pot[n + p], -gain); }
    });
    for (let p = 0; p < nPages; p++) pot[T] = Math.min(pot[T], pot[n + p]);   // shortest distances: reduced costs >= 0
    const reduced = e => cost[e] + pot[to[e ^ 1]] - pot[to[e]];
    const dist = new Float64Array(V), done = new Uint8Array(V), level = new Int32Array(V), it = new Int32Array(V);
    const hk = new Float64Array(E + V), hv = new Int32Array(E + V), queue = new Int32Array(V), path = new Int32Array(V);
    for (;;) {
      dist.fill(Infinity); done.fill(0);                       // Dijkstra on reduced costs, to T
      dist[S] = 0;
      let size = 0;
      const push = (k, v) => {
        let i = size++;
        while (i > 0) { const p = (i - 1) >> 1; if (hk[p] <= k) break; hk[i] = hk[p]; hv[i] = hv[p]; i = p; }
        hk[i] = k; hv[i] = v;
      };
      push(0, S);
      while (size) {
        const d = hk[0], v = hv[0], k = hk[--size], x = hv[size];
        let i = 0;
        for (;;) {
          let c = 2 * i + 1;
          if (c >= size) break;
          if (c + 1 < size && hk[c + 1] < hk[c]) c++;
          if (hk[c] >= k) break;
          hk[i] = hk[c]; hv[i] = hv[c]; i = c;
        }
        hk[i] = k; hv[i] = x;
        if (done[v]) continue;
        done[v] = 1;
        if (v === T) break;
        for (let e = head[v]; e >= 0; e = next[e]) {
          if (!res[e]) continue;
          const u = to[e], nd = d + reduced(e);
          if (nd < dist[u]) { dist[u] = nd; push(nd, u); }
        }
      }
      if (dist[T] === Infinity) break;
      for (let v = 0; v < V; v++) pot[v] += Math.min(dist[v], dist[T]);
      if (pot[T] - pot[S] >= 0) break;                         // the cheapest path gains nothing
      for (;;) {                                               // blocking flows on the arcs of reduced cost 0
        level.fill(-1); level[S] = 0;
        let qa = 0, qb = 0;
        queue[qb++] = S;
        while (qa < qb) {
          const v = queue[qa++];
          for (let e = head[v]; e >= 0; e = next[e]) if (res[e] && level[to[e]] < 0 && reduced(e) === 0) { level[to[e]] = level[v] + 1; queue[qb++] = to[e]; }
        }
        if (level[T] < 0) break;
        it.set(head);
        let depth = 0, v = S;                                  // every path carries one unit (word arcs have capacity 1)
        for (;;) {
          if (v === T) {
            for (let k = 0; k < depth; k++) { res[path[k]]--; res[path[k] ^ 1]++; }
            depth = 0; v = S;
            continue;
          }
          let e = it[v];
          while (e >= 0 && !(res[e] && level[to[e]] === level[v] + 1 && reduced(e) === 0)) e = next[e];
          it[v] = e;
          if (e >= 0) { path[depth++] = e; v = to[e]; continue; }
          if (v === S) break;
          level[v] = -1;                                       // a dead end for this phase
          v = to[path[--depth] ^ 1];
          it[v] = next[it[v]];
        }
      }
    }
    return wordArcs.map(a => { const hit = a.find(([e]) => !res[e]); return hit ? hit[1] : -1; });
  }

  /** Per page, the tokens that contain each word: Map word -> count, computed once for a book's pages. */
  const COUNTS = new WeakMap();
  function pageCounts(doc, pages) {
    if (!COUNTS.has(pages)) COUNTS.set(pages, pages.map(pg => {
      const here = new Map();
      for (const s of pageSentences(doc, pg)) for (const t of s.tokens) {
        if (t.key === null) continue;
        for (const w of new Set([t.key, ...t.extra])) here.set(w, (here.get(w) || 0) + 1);
      }
      return here;
    }));
    return COUNTS.get(pages);
  }

  /** The words to introduce on each page from page `from` on: each word worth learning that is not
   * done goes to at most one page where it occurs, at most `perPage` a page, so as to avoid the most
   * hints (a word introduced on page p saves its occurrences from p on). Exact (assignPages) over
   * the next `horizon` pages; a word can also be left for the pages after them, which are assumed to
   * have room for it. bench/pages_bench.py measures it against introductionsOn. Returns Map word ->
   * page, for the pages of the horizon. */
  function introductionPlan(doc, pages, learned, isDone, perPage, from = 0, horizon = HORIZON) {
    const end = Math.min(pages.length, from + horizon), idx = new Map(), words = [], gains = [], later = [], rest = new Map();
    const counts = pageCounts(doc, pages);
    for (let p = pages.length - 1; p >= from; p--) {                // occurrences from p on, walking back
      for (const [w, c] of counts[p]) {
        if (!learned.has(w) || isDone(w)) continue;
        if (p < end && !idx.has(w)) { idx.set(w, words.length); words.push(w); gains.push([]); later.push(rest.get(w) || 0); }
        rest.set(w, (rest.get(w) || 0) + c);
        if (p < end) gains[idx.get(w)].push([p - from, rest.get(w)]);
      }
    }
    // what introducing on a page saves over leaving the word for later: its occurrences from that
    // page to the end of the horizon
    gains.forEach((g, i) => { for (const x of g) x[1] -= later[i]; });
    const at = assignPages(gains, end - from, perPage), plan = new Map();
    words.forEach((w, i) => { if (at[i] >= 0) plan.set(w, at[i] + from); });
    return plan;
  }

  /** The words page p introduces, for a reader going forward: `introducer(...)(p)`, in reading
   * order. A book whose words and pages make a small enough problem is planned whole, exactly;
   * a larger one `horizon` pages ahead (introductionPlan), planned again halfway through. It plans
   * again when a page is opened out of order; `isDone` is asked again on each page. */
  function introducer(doc, pages, learned, isDone, perPage, horizon = null) {
    let plan = null, from = 0, next = -1, ahead = 0;
    const counts = pageCounts(doc, pages);
    return p => {
      if (!plan || p !== next || p >= from + Math.ceil(ahead / 2)) {
        ahead = horizon;
        if (ahead === null) {                                     // the size of the whole problem from p
          let arcs = 0;
          for (let q = p; q < pages.length && arcs <= EXACT_ARCS; q++) for (const w of counts[q].keys()) if (learned.has(w) && !isDone(w)) arcs++;
          ahead = arcs <= EXACT_ARCS ? Infinity : HORIZON;
        }
        plan = introductionPlan(doc, pages, learned, isDone, perPage, p, ahead);
        from = p;
      }
      next = p + 1;
      const out = [];
      for (const s of pageSentences(doc, pages[p])) for (const w of wordsOf(s)) if (plan.get(w) === p && !isDone(w) && !out.includes(w)) out.push(w);
      return out;
    };
  }

  /** Occurrences of each word from page `from` on. */
  function occurrencesFrom(doc, pages, from = 0) {
    const occ = new Map();
    for (let p = from; p < pages.length; p++) for (const s of pageSentences(doc, pages[p])) for (const w of wordsOf(s)) occ.set(w, (occ.get(w) || 0) + 1);
    return occ;
  }

  /** Reading the whole book from `fromPage` with `known` words: per page, the share of its words
   * the reader knows before it, the words it introduces, and the words that get a hint. Pages
   * introduce words by introductionPlan, or with `greedy` by introductionsOn. */
  function simulate(doc, pages, learned, known, perPage, fromPage = 0, introduced = new Set(), {greedy = false, horizon = null} = {}) {
    const met = new Set(introduced), out = [], occ = occurrencesFrom(doc, pages, fromPage);
    const isDone = w => known.has(w) || met.has(w), intro = introducer(doc, pages, learned, isDone, perPage, horizon);
    for (let p = fromPage; p < pages.length; p++) {
      const fresh = greedy ? introductionsOn(doc, pages[p], learned, isDone, perPage, occ) : intro(p);
      for (const s of pageSentences(doc, pages[p])) for (const w of wordsOf(s)) occ.set(w, occ.get(w) - 1);
      let tok = 0, knownTok = 0, hinted = 0;
      for (const s of pageSentences(doc, pages[p])) for (const t of s.tokens) {
        if (t.key === null) continue;
        tok++;
        const ws = [t.key, ...t.extra];
        if (ws.every(w => known.has(w) || met.has(w))) knownTok++;
        else if (!ws.some(w => fresh.includes(w))) hinted++;
      }
      for (const w of fresh) met.add(w);
      out.push({page: p, known: tok ? knownTok / tok : 1, introduced: fresh.length, hinted, tokens: tok});
    }
    return out;
  }

  /** Memory of a word being learned, with time counted in pages: on page p the reader recalls it
   * with probability 2^(-(p - t) / h), t the page of its last event and h its half-life in pages
   * (half-life regression, Settles & Meeder 2016). Events: "i" introduced; "s" met with its meaning
   * hidden and not tapped; "h" met with its meaning shown; "t" tapped for its meaning (forgotten);
   * "r" and "f" remembered and forgotten on a review card. A success multiplies h by more the less
   * likely recall was, and meeting the word in the text counts `passive` of a card; a lapse divides
   * it. The page shows the meaning below recall `show` and asks the reader to recall it (meaning on
   * tap) below `check`. The numbers are starting guesses, to fit from readers' events. */
  const MEMORY = {h0: 6, hMin: 2, passive: 0.3, base: 0.5, boost: 4, lapse: 0.4, show: 0.5, check: 0.9};
  const recall = (m, p) => m ? Math.pow(2, -Math.max(0, p - m.t) / m.h) : 0;
  /** The memory after an event on page p ({h, t}, or undefined for a word not introduced). */
  function remember(m, p, code) {
    if (code === "i") return {h: MEMORY.h0, t: p};
    if (!m || p < m.t) return m;                               // before the word was met: nothing to learn
    const r = recall(m, p), M = MEMORY;
    if (code === "s" || code === "r") return {h: m.h * (1 + (code === "s" ? M.passive : 1) * (M.base + M.boost * (1 - r))), t: p};
    if (code === "t" || code === "f") return {h: Math.max(M.hMin, m.h * M.lapse), t: p};
    if (code === "h") return {h: m.h, t: p};
    return m;
  }
  /** Memory of each word from its events, {word: ["12i", "14s", ...]} in the order they happened. */
  function memoryOf(events) {
    const mem = new Map();
    for (const [w, evs] of Object.entries(events)) {
      let m;
      for (const e of evs) m = remember(m, parseInt(e, 10), e[e.length - 1]);
      if (m) mem.set(w, m);
    }
    return mem;
  }

  const api = {pagesOf, pageSentences, pageCounts, introductionsOn, assignPages, introductionPlan, introducer, occurrencesFrom, simulate,
               MEMORY, recall, remember, memoryOf, loadLanguage, lemmaOf, stripGutenberg, splitParagraph, tokenSpans, isHeading, paragraphsFromText,
               analyze, sessionsOf, wordsOf, storyUnits, rentOrBuyRule, greedy, unlockOrder, buildCourse, courseStats,
               tradeoff, rankedLemmas, knownKeys, shortGloss, glossOf, packData, KEEP};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.Readfirst = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
