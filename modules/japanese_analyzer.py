from collections import Counter
from typing import List

from janome.tokenizer import Tokenizer


def load_stopwords(path: str) -> set:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return {line.strip() for line in f if line.strip()}
    except FileNotFoundError:
        return set()


def extract_keywords(
    text: str,
    max_keywords: int,
    parts_of_speech: List[str],
    min_frequency: int,
    stopwords_path: str,
) -> List[str]:
    if not text:
        return []

    tokenizer = Tokenizer()
    stopwords = load_stopwords(stopwords_path)
    tokens = []
    display_map = {}

    for token in tokenizer.tokenize(text):
        pos = token.part_of_speech.split(",")[0]
        if pos != "動詞":
            continue

        base = token.base_form
        surface = token.surface
        value = base if base != "*" else surface

        if value in stopwords:
            continue

        reading = token.reading if token.reading != "*" else ""
        display = f"{value}（{reading}）" if reading else value

        tokens.append(value)
        display_map.setdefault(value, display)

    counts = Counter(tokens)
    filtered = [word for word, cnt in counts.items() if cnt >= min_frequency]
    filtered.sort(key=lambda w: counts[w], reverse=True)

    return [display_map[word] for word in filtered[:max_keywords]]

