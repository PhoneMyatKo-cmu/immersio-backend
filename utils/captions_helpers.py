import html
import re
from copy import deepcopy

from fugashi import Tagger

# Punctuation marks to exclude from word lookups
PUNCTUATION = {"。", "．", "！", "？", "!", "?", "…", "、", ","}

tagger = Tagger()


def get_line_level_captions(captionData: dict):

    snippets = []
    index = 0

    for event in captionData.get("events", []):
        if "segs" not in event:
            continue

        # Aggregate sub-segments into one line
        raw_text = "".join(s.get("utf8", "") for s in event["segs"])

        # Skip newline-only events
        if not raw_text.strip() or raw_text == "\n":
            continue

        # Normalize: decode HTML entities, collapse whitespace
        text = html.unescape(raw_text)
        text = re.sub(r"\s+", " ", text).strip()

        if not text:
            continue

        snippets.append(
            {
                "index": index,
                "text": text,
                "start": round(event.get("tStartMs", 0) / 1000.0, 3),
                "duration": round(event.get("dDurationMs", 0) / 1000.0, 3),
            }
        )
        index += 1

    # Deduplicate rolling overlap (matters for auto-generated captions)
    snippets = _deduplicate_rolling(snippets)

    # Re-index after dedup
    for i, snippet in enumerate(snippets):
        snippet["index"] = i

    return snippets


def _deduplicate_rolling(snippets):
    """Remove rolling-caption overlap common in auto-generated content."""
    if not snippets:
        return snippets

    cleaned = [snippets[0]]
    for snippet in snippets[1:]:
        prev = cleaned[-1]
        current_text = snippet["text"]

        if current_text.startswith(prev["text"]) and len(current_text) > len(
            prev["text"]
        ):
            cleaned[-1] = snippet
        elif prev["text"].startswith(current_text):
            continue
        else:
            cleaned.append(snippet)

    return cleaned


def analyse_token(text):
    tokens = []
    node_list = tagger.parseToNodeList(text)

    for node in node_list:
        if node.surface and node.surface.strip():
            token_features = node.feature
            is_content_token = is_content_word(node)
            token_base_form = (
                token_features.lemma if token_features.lemma != "*" else node.surface
            )
            token_pos = token_features.pos1
            token_pos_detail = token_features.pos2

            lemma = str(token_features.lemma)
            if lemma == "*" or lemma is None:
                lemma = node.surface
            else:
                lemma = lemma.split("-")[0]  # dictionary form (lemma) of the token
            tokens.append(
                {
                    "surface": node.surface,
                    "base_form": token_base_form,
                    "lemma": lemma, # dictionary form (lemma) of the token
                    "pos": token_pos,  # Part of speech
                    "pos_detail": token_pos_detail,  # POS subcategory
                    "is_content_word": is_content_token,
                }
            )

    return tokens


def tokenize_captions(raw_captions: list[dict]):
    tokenized_captions = raw_captions
    for caption in tokenized_captions:
        caption["tokens"] = analyse_token(caption["text"])
    return tokenized_captions


# =========================================================
# 1. TIMESTAMP NORMALIZATION
# =========================================================


def normalize_captions_fragments(fragments, min_gap=0.05):
    """
    Remove overlapping timestamps.

    Input:
    {
        "text": str,
        "start": float,
        "duration": float
    }

    Output:
    {
        "text": str,
        "start": float,
        "end": float,
        "duration": float
    }
    """

    normalized = deepcopy(fragments)

    for i in range(len(normalized)):
        frag = normalized[i]

        start = float(frag["start"])
        end = start + float(frag.get("duration", 0))

        # compare against next fragment
        if i < len(normalized) - 1:
            next_start = float(normalized[i + 1]["start"])

            if end > next_start:
                end = max(start, next_start - min_gap)

        frag["start"] = round(start, 3)
        frag["end"] = round(end, 3)
        frag["duration"] = round(end - start, 3)

    return normalized


def is_japanese(text):
    return re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", text) is not None


def is_content_word(word):
    """
    Determines if a word should be lookup-able by users.

    Returns False only for:
    - Non-Japanese text
    - Punctuation marks

    All other Japanese words (particles, auxiliaries, etc.) return True
    to allow learners to look up any word they encounter.
    """
    if not is_japanese(word.surface):
        return False

    if word.surface in PUNCTUATION:
        return False

    return True


def process_captions(raw_captions: list[dict]) -> list[dict]:
    normalized_captions = normalize_captions_fragments(raw_captions)
    return tokenize_captions(normalized_captions)
