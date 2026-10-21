# Readfirst

Which words should you learn first to read a particular book, and how do you get from there to
reading it?

Readfirst does two things with one book:

- **The plan.** It orders the book's vocabulary so whole sentences become readable as early as
  possible, and proves how close that order is to the best possible.
- **The course.** It turns the book into a course: study a few words, read a few pages, repeat.
  Each word is learned just before the first page that uses it, and every other word is glossed in
  place. The output is a study pack: a reader page, an Anki deck in study order, and a word list.

```
$ python -m readfirst course books/es-marianela.txt --lang es --title Marianela --out pack/
Marianela: 50 sessions; learn 2,684 words (15 a day), gloss the rest (12.52 a page, 95.0% of the text known while reading).
First page on day 12, last page on day about 205.
comfort      words to learn   glosses a page
  comfortable       3,405          7.3
  balanced          2,684         12.5
  fast              2,230         16.6
wrote pack/reader.html, pack/deck.apkg (2684 cards), pack/words.tsv
```

**Pages:** the app is https://claude.ai/artifact/WLfrAf3dbR4b5KB1HPnRD9, the project page is
https://claude.ai/artifact/JgKZGW3w3wE5a4cokwQVgy, and the Marianela study pack is
https://claude.ai/artifact/T8uvS8tRPfhSo6mHTQTtoL. All three are private until you share them from
their Share menu.

## The app

`app/` is Readfirst as a web app that runs entirely in the browser, for learners who will not
install anything. It is built around reading, not flashcards:

1. **Open a book**: a DRM-free EPUB or a text file, or one of four public-domain samples. The book
   is read in the browser and never uploaded; Readfirst detects the language and where the story
   starts (both can be changed).
2. **Answer one question**: how much of the language you know, in plain words (just starting, some
   basics, simple texts, reading with a dictionary), each answer showing the share of the opening
   you would already know. Choosing one shows what reading this book will be like ("62% of the
   words on the first page, 72% by page 20 and 92% near the end, learning 1,458 words along the
   way"). A one-minute word check (35 of the book's words, from the 250 most common words of the
   language to the 16,000th) is there for anyone unsure.
3. **Read.** The story comes in screen-sized pages of about 220 words. Each page introduces at most
   8 words worth learning (5 or 12 in the settings), highlighted with their meaning under them:
   the words on the page that the rest of the book uses most. A word being learned keeps a faded
   meaning under it for the next two pages, then only an underline. Every other unknown word has a
   short hint under it (or on tap). Tap any word for its meaning, "I know this word", and a
   Wiktionary link. Below the text, "New on this page" lists the page's words, each with "I knew
   it".
4. **Review, if you like**: words come back the day after you meet them, in their sentence from the
   book, then after 3, 7, 16, 35 and 80 days. A badge shows how many are due; reading never waits
   for it.

Everything else is in the menu: the contents (jump to a chapter), new words per page, hints under
words or on tap, changing your level, pasting words you know, "Export to Anki" (tab-separated, with
the example sentences) and "Back up progress" (a file to restore in another browser). Progress stays
in the browser (local storage, the book in IndexedDB).

Which words are worth learning is the rule below (learn every word met six times, then patch
sentences that would need more than two hints), applied to what you know plus what you have met;
the pages then hand those words out, at most 8 a page. With 8 a page, a few words worth learning
never get a free slot and stay hinted (97 of 606 in Alice from 1,000 words; `app/test/check_pages.js`
checks the pages and the per-page counts). A word with no meaning in the dictionary is never
introduced. On top of the shared analysis, the app reads chapter headings written as a bare Roman
numeral ("-II-") with the title under them, treats the parts of a hyphenated name
(*Thunder-ten-tronckh*) and capitalized German words no dictionary knows (*Gregor*, *Samsa*) as names,
reads older French spellings (*fesait*, *étoit*) as modern ones, and finds meanings for Spanish words
with attached pronouns (*ponerse*, *díjole*) or diminutive endings (*ojuelos*) and for German
compounds (*Fensterblech*: window + sheet metal).

**The same engine, in JavaScript.** `app/engine.js` ports the text analysis, the course and the
study pack, and adds the pages. `app/test/check_engine.js` runs it on the four samples against the Python
implementation (`app/test/export_reference.py`):

- the same paragraphs, headings, sentences, tokens with their positions, names and story start;
- given the same dictionary forms, exactly the same course (words to learn, parts, study lists in
  order, glosses), the same example sentences and the same general frequency ranking, from zero
  and knowing 1,000 words.

Two things differ. The browser chooses words with the rule (learn every word met six times, then
patch sentences that need too many glosses), which costs 0% to 1.2% more words than the integer
program. And it lemmatizes with a table: simplemma applied to the 150,000 most common written
forms of each language (wordfreq), shipped as `app/data/<lang>.json` (0.9 to 4.8 MB, 0.3 to 1.4 MB
gzipped). For French it also takes the rarer inflected forms Wiktionary lists (passé simple,
imperfect subjunctive: *baisa*, *fussions*). It agrees with Python's lemmatizer on 98.9%
(Marianela), 99.9% (Candide), 98.7% (Die Verwandlung) and 99.9% (Alice) of tokens; the rest are
rare forms (archaic enclitics such as *hallábase*, German compounds such as *Zimmerherren*), which
the browser counts as words of their own. That adds up to 3.4% to the words to learn.

In the browser, the share of a French book's words to gloss or learn that have a meaning went from
49–58% with FreeDict to 96–97% with Wiktionary (Candide, Le tour du monde, Monte-Cristo I); weighted
by how often they occur, from 90–92% to 99–99.7%.

## The plan: sentences first

Learn one word per step. A sentence becomes readable at the step its last unknown word is learned.
To make sentences readable as early as possible, minimise

    sum over sentences of (the step at which its last word is learned)

That is single-machine scheduling with precedence constraints, `1 | prec | Σ wⱼCⱼ`. Words are
unit-length jobs of weight 0, and each sentence is a zero-length job of weight 1 that must come after
all of its words.

- **Densest clusters first.** Sidney (1975) showed that good schedules come in blocks. First take the
  set of words that completes the most sentences per word, then do the same on what remains. That set
  is a densest sub-hypergraph, a maximum-weight closure, which one max-flow finds exactly (Picard
  1976). Any order that respects the blocks is within a factor of two of optimal (Chekuri & Motwani
  1999; Margot, Queyranne & Wang 2003). Inside a block, Readfirst picks greedily: next, the word that
  completes the most sentences.
- **A proof comes with it.** Let g(k) be the most sentences any k words can make readable. The block
  boundaries are the corners of g's upper concave envelope. So no order can beat the envelope at any
  k, and the block order meets it at every corner. That gives the "fewest possible" row in the table
  below, a lower bound on the words any order needs to reach a given share.

The table covers eleven public-domain books, for a learner starting from zero. `bench/results.json`
also has each book for a learner who already knows the 1,000 most common words.

| Book | Words | Sentences | 50%: fewest possible | this plan | frequency order | 90%: fewest possible | this plan | frequency order |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Alice's Adventures in Wonderland (en) | 1,851 | 1,370 | 648 | 648 | 832 (+28%) | 1,389 | 1,389 | 1,693 (+22%) |
| Stories to Tell to Children (en) | 2,733 | 2,582 | 902 | 903 | 1,089 (+21%) | 2,070 | 2,070 | 2,433 (+18%) |
| The Innocence of Father Brown (en) | 5,446 | 3,579 | 1,760 | 1,760 | 2,608 (+48%) | 4,247 | 4,249 | 5,039 (+19%) |
| Emma (en) | 4,774 | 6,972 | 1,227 | 1,227 | 1,361 (+11%) | 3,398 | 3,398 | 3,936 (+16%) |
| Metamorphosis (en) | 1,997 | 769 | 815 | 817 | 1,297 (+59%) | 1,620 | 1,625 | 1,908 (+17%) |
| Marianela (es) | 4,676 | 3,217 | 1,118 | 1,118 | 1,646 (+47%) | 3,304 | 3,306 | 4,300 (+30%) |
| Don Quijote (es) | 9,326 | 10,239 | 2,761 | 2,762 | 3,267 (+18%) | 6,816 | 6,818 | 8,117 (+19%) |
| Candide (fr) | 3,401 | 1,411 | 1,189 | 1,190 | 2,005 (+68%) | 2,623 | 2,624 | 3,236 (+23%) |
| Le tour du monde en 80 jours (fr) | 5,316 | 4,200 | 1,499 | 1,499 | 2,014 (+34%) | 3,801 | 3,801 | 4,815 (+27%) |
| Le Comte de Monte-Cristo I (fr) | 6,066 | 5,640 | 1,680 | 1,680 | 2,165 (+29%) | 4,401 | 4,401 | 5,385 (+22%) |
| Die Verwandlung (de) | 2,845 | 625 | 1,017 | 1,018 | 2,322 (+128%) | 2,267 | 2,283 | 2,780 (+22%) |

How close the plan comes to the proven minimum, across all 22 runs:

| Share of sentences | Furthest from the minimum |
|---|---|
| 50% | 2 words |
| 75% and 90% | within 1% |
| 25% | within 5% |

Learning the book's most frequent words first needs 11% to 181% more words to read half the
sentences. A plain greedy order without blocks is already 0–5% above the minimum. The envelope is
what shows how good both are.

James Tauber posed this ordering problem, for the Greek New Testament, as a programming competition.

## The course: read the book, in order

The plan opens sentences from all over the book, but a learner wants to read the story. So the
course cuts the story into sessions, about one page at first, then two, three and up to four.

1. **Learn just before the pages that use a word.** Before each session, the learner studies the
   session's words worth learning and reads with glosses for the rest.
2. **Decide what is worth learning as rent or buy.** A word can be glossed every time it appears
   (rent) or learned once with a flashcard (buy, counted as `--learn-cost` look-ups, 6 by default).
   Each word alone is simple: buy it if it appears six times or more. What couples the words is
   comfort: no sentence may need more than one, two or three glosses (`--comfort`). Readfirst solves
   the whole book at once as an integer program (OR-Tools CP-SAT), with a proven optimum in a second
   or less, even for Don Quijote:

       minimise   6 × words learned + occurrences of words not learned
       subject to every sentence has at most `cap` unknown words left

3. **Study in an order that opens the coming pages.** A session's list is studied in the order that
   makes its sentences readable soonest: the plan's greedy, applied to the session. Each word comes
   with an example from those pages, the sentence it completes where there is one.

The course for each book, from zero, at 15 new words a day and one session a day once its words are
learned:

| Book | Words in the story | Learn (comfort 1 / 2 / 3) | Glosses a page (1 / 2 / 3) | First page (2) | Last page (2) |
|---|---:|---:|---:|---:|---:|
| Alice's Adventures in Wonderland | 1,860 | 1,360 / 1,103 / 953 | 5.7 / 10.1 / 13.2 | day 9 | day 91 |
| Stories to Tell to Children | 2,736 | 1,885 / 1,462 / 1,222 | 5.8 / 10.2 / 13.3 | day 5 | day 122 |
| The Innocence of Father Brown | 5,459 | 3,862 / 2,942 / 2,381 | 6.4 / 11.5 / 15.5 | day 11 | day 233 |
| Emma | 4,797 | 3,292 / 2,632 / 2,266 | 3.1 / 5.2 / 6.6 | day 10 | day 283 |
| Metamorphosis | 1,995 | 1,521 / 1,224 / 1,023 | 5.7 / 10.0 / 13.7 | day 12 | day 91 |
| Marianela | 4,701 | 3,405 / 2,684 / 2,230 | 7.3 / 12.5 / 16.6 | day 12 | day 205 |
| Don Quijote | 9,213 | 6,312 / 4,967 / 4,230 | 2.4 / 4.1 / 5.2 | day 14 | day 576 |
| Candide | 3,326 | 2,548 / 2,060 / 1,727 | 6.0 / 10.8 / 14.9 | day 9 | day 158 |
| Le tour du monde en 80 jours | 5,316 | 3,750 / 2,944 / 2,455 | 6.4 / 11.2 / 14.7 | day 9 | day 244 |
| Le Comte de Monte-Cristo I | 6,063 | 4,383 / 3,532 / 3,003 | 3.9 / 6.8 / 9.0 | day 8 | day 304 |
| Die Verwandlung | 2,800 | 2,309 / 1,931 / 1,643 | 6.5 / 11.8 / 16.2 | day 11 | day 135 |

`bench/course_results.json` has the same for a learner who already knows 1,000 common words. For
that learner the first page comes on day 1 to 6.

### What the experiments decided

Each design choice above was measured first (`bench/course_bench.py`, `bench/unlock_bench.py`).

- **Comfort decides most of the cost.** At one gloss per sentence (about 97% of the text known while
  reading), a novel needs 69% to 82% of its distinct words learned. That is the long tail of rare
  words, and at that setting fewer than half the learned words come back three or more times
  afterwards. Allowing three glosses cuts the words to learn by 29% to 38%. The default allows two,
  which is about 95% of the text known: the level reading research gives for reading with support.
  The pack shows the trade-off and the choice is the learner's.
- **The exact choice is only slightly better than the obvious rule.** The rule is: learn every word
  met six times, then patch any sentence that needs too many glosses. It costs 0% to 1.2% more. The
  integer program earns its place by proving that, not by large savings.
- **The order of study matters while studying.** In Readfirst's order, 66% to 80% of a session's
  sentences are readable on average while its list is being studied. Studying the same list most
  frequent first gives 44% to 65%. Measured on Alice, Marianela, Le tour du monde and Die Verwandlung.
- **A book-wide head start does not pay.** Learning the plan's first 1,000 words before the story
  pushes Marianela's first page from day 12 to day 71, and adds 142 words to the course. It lowers
  glosses from 12.5 to 10.5 a page. So the course starts with the story, and the plan stays the tool
  for sentence practice.

## Meanings

`python -m readfirst.dictionary fetch` downloads the sources and compiles short glosses into
`dicts/`. The compiled files are not part of this repository and keep their sources' licences.

| Language | Source | Licence | Share of the 2,000 most used words glossed |
|---|---|---|---|
| Spanish | Wiktionary, via doozan/spanish_data | CC BY 4.0 | 98% |
| German | Ding, TU Chemnitz (Debian package `trans-de-en`), nouns with their article | GPL 2+ | 89% |
| French | Wiktionary, via kaikki.org and Vuizur/Wiktionary-Dictionaries; FreeDict fra-eng for the gaps | CC BY-SA 3.0; GPL 2 | 98% (75% with FreeDict alone) |
| English | WordNet 3.0, as English definitions | WordNet licence | 95% |

A few dozen function words per language that the sources lack or gloss badly are written by hand
(`OVERRIDES`). Every word in the reader also links to Wiktionary.

## Words, names and sentences

- **A word is a dictionary form** (lemma, from simplemma): learning *decir* counts as knowing *dijo*.
  Personal pronouns stay separate words, because simplemma folds *usted* into *tú* and *te* into
  *le*. Spanish verbs with attached pronouns count as their parts: *darle* is *dar* + *le*.
- **Names are free.** A capitalised word the book never writes in lower case counts as a name. German
  capitalises every noun, so in German nothing counts as a name.
- **The story starts at the first chapter heading followed by prose.** So title pages, tables of
  contents and editors' prefaces are skipped. The plan counts sentences of three or more words; the
  course reads everything from the start of the story.

## How the claims are checked

`python -m pytest tests` runs 986 tests in about 8 seconds.

- **The envelope** is never below the true best coverage, found by trying every set of words on 300
  random small books. It equals that coverage at every corner and is strictly concave. The block
  order meets every corner, and its cost is at most twice the optimum found by trying every order.
- **Rent or buy** matches the best choice found by trying every set of words on 120 random small
  books, and always keeps each sentence within its limit. The simple rule never beats it.
- **The course on a real book**, at every comfort level:
  - each word is taught exactly once, in the session where it first appears;
  - no sentence needs more glosses than allowed;
  - the glosses add up.
- **The pack:** the Anki deck has one card per word, in study order, and the reader's marks stay
  inside their sentences.
- **Text:** sentence splitting, French elision, names, German nouns, Spanish clitics, and the three
  dictionary parsers.

On the real books, `python -m bench.check_ilp BOOK PERCENT` checks a claimed minimum with CP-SAT.
With one word fewer than the claim, no choice of words reaches the target. Confirmed:

| Book | Share of sentences | Minimum |
|---|---|---|
| Alice | 50% | 648 words |
| Die Verwandlung | 50% | 1,017 words |
| Marianela | 75% | 2,204 words |

## Use it

The app needs nothing installed: open its page. To build it and host it yourself (any static web
server; `app/site/` is the complete site, `app/dist/` the same page for publishing as a Claude
artifact). Neither is in the repository, since the data is compiled from the dictionaries; install
the Python package below first:

```
python app/build_data.py          # app/data/<lang>.json, after `python -m readfirst.dictionary fetch`
python app/build_app.py           # app/dist/ and app/site/
python app/test/export_reference.py && node app/test/check_engine.js
node app/test/check_pages.js
python -m http.server -d app/site 8000
```

The Python package (tested with Python 3.13):

```
pip install -r requirements.txt
python -m readfirst.dictionary fetch
python -m readfirst course my-book.txt --lang es --out pack/                 # the study pack
python -m readfirst course my-book.txt --lang de --comfort comfortable --know-top 1000 --out pack/
python -m readfirst my-book.txt --lang es --know-top 1000 --plan plan.tsv    # the sentence plan
```

`course` options:

| Option | What it sets |
|---|---|
| `--comfort comfortable \| balanced \| fast` | at most 1, 2 or 3 glosses per sentence |
| `--daily N` | new words a day |
| `--learn-cost N` | how many look-ups a flashcard is worth |
| `--know-top N` or `--known FILE` | words already known |

What the pack contains:

- `reader.html` opens offline. It shows each session's words with meanings and examples, then the
  pages with glosses under the words (or on tap). It remembers where you are.
- `deck.apkg` imports into Anki, with new cards in study order and tagged by session.
- `words.tsv` is the same list as a table.

To rebuild everything:

```
python -m bench.run             # the plan, ~4 min
python -m bench.course_bench    # the course, ~30 s
python web/build.py
PYTHONPATH=. python web/build_reader.py
```

## Files

```
readfirst/text.py         the book in reading order: paragraphs, sentences, tokens, lemmas, names
readfirst/order.py        the plan: curves, orders, densest blocks, the envelope bound
readfirst/course.py       the course: sessions, rent-or-buy, study order
readfirst/pack.py         the study pack: reader data, Anki deck, word list
readfirst/dictionary.py   fetching and compiling the meanings
readfirst/general.py      a general frequency list mapped onto a book's lemmas
readfirst/plan.py         the sentence plan's example sentences
readfirst/__main__.py     the command line
app/engine.js             the course engine in JavaScript (browser and Node)
app/src/index.html        the app: import, level check, flashcards, reader, progress
app/build_data.py         word forms, frequencies and meanings for the browser
app/build_app.py          assembles app/dist/ and app/site/
app/test/                 the Python reference export and the JavaScript checks
bench/                    benchmarks and their results; check_ilp.py
books/                    the eleven books (Project Gutenberg, via GITenberg and NLTK)
tests/                    the checks above
web/                      the project page and the Marianela study pack
```

## Licence

The code is under the MIT licence (`LICENSE`). The books are public domain, from Project
Gutenberg. The dictionaries that `fetch` compiles, and the app data built from them, keep their
sources' licences (see Meanings) and are not part of this repository. The one exception is the
Marianela study pack, `web/marianela-reader.html`, whose glosses come from Wiktionary via
doozan/spanish_data (CC BY 4.0).
