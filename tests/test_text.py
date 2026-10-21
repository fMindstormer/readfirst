from readfirst.text import build, split_sentences, strip_gutenberg, tokens


def test_sentence_split():
    s = split_sentences('Mr. Smith went home. He said: «Bonjour!» Then—¿Qué dices? —preguntó él. "Yes," she said.\n\nNew paragraph')
    assert s == ['Mr. Smith went home.', 'He said: «Bonjour!»', 'Then—¿Qué dices? —preguntó él.', '"Yes," she said.', 'New paragraph']


def test_french_elision_and_pronouns():
    assert tokens("L'homme qu'il aime", "fr") == ["L'", "homme", "qu'", "il", "aime"]
    b = build("Je te vois. L'homme te regarde. Il te parle.", "fr")
    words = set().union(*(s.words for s in b.sentences))
    assert {"le", "homme", "que", "te"} - {"que"} <= words and "le" in words
    assert "te" in words                      # not folded into "le"


def test_names_are_free_but_not_german_nouns():
    b = build("Alice saw the cat. The cat saw Alice too. Then Alice ran away.", "en")
    assert "Alice" in b.names and all("alice" not in s.words for s in b.sentences)
    d = build("Gregor sah das Zimmer. Das Zimmer war klein. Er sah das Zimmer an.", "de")
    assert not d.names
    assert any("Zimmer" in s.words for s in d.sentences)      # nouns keep their capital
    assert any("das" in s.words or "der" in s.words for s in d.sentences)


def test_identical_sentences_merge():
    b = build("The cat sat down. The cat sat down. A dog ran off.", "en")
    assert sorted(s.count for s in b.sentences) == [1, 2]


def test_gutenberg_frame_is_stripped():
    text = ("The Project Gutenberg EBook of Candide\n\n*** START OF THIS PROJECT GUTENBERG EBOOK CANDIDE ***\n\n"
            "Il était une fois.\n\nEnd of the Project Gutenberg EBook of Candide, by Voltaire\n\n"
            "*** END OF THIS PROJECT GUTENBERG EBOOK CANDIDE ***\n\nLicence text.")
    assert strip_gutenberg(text).strip() == "Il était une fois."
