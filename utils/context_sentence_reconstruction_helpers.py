import re

SENTENCE_END_PUNCTUATION = re.compile(r"[。！？!?…]")

POLITE_ENDINGS = {
    "です",
    "ます",
    "でした",
    "ました",
    "ません",
    "だ",
    "ください",
"下さい",
"ましょう",
}

FINAL_PARTICLES = {
    "ね",
    "よ",
    "か",
    "な",
    "ぞ",
    "ぜ",
    "わ",
}


# =========================================================
# 2. BOUNDARY SCORING
# =========================================================

def boundary_score(
    current_text: str,
    gap: float,
    duration: float,
    max_duration: float,
):
    """
    Higher score => more likely sentence boundary.
    """

    score = 0

    stripped = current_text.strip()

    # -------------------------------------
    # Strong punctuation signal
    # -------------------------------------
    if SENTENCE_END_PUNCTUATION.search(stripped):
        score += 5

    # -------------------------------------
    # Polite ending
    # -------------------------------------
    if any(stripped.endswith(x) for x in POLITE_ENDINGS):
        score += 2

    # -------------------------------------
    # Final particle
    # -------------------------------------
    if any(stripped.endswith(x) for x in FINAL_PARTICLES):
        score += 1

    # -------------------------------------
    # Pause signal
    # -------------------------------------
    if gap >= 1.0:
        score += 2

    if gap >= 2.0:
        score += 4

    # -------------------------------------
    # Duration pressure
    # -------------------------------------
    if duration >= max_duration * 0.7:
        score += 1

    if duration >= max_duration:
        score += 100  # hard flush

    return score


# =========================================================
# 3. BUILD SENTENCE
# =========================================================

def build_sentence(group, sentence_index):
    if not group:
        return None

    text = "".join(x["text"].strip() for x in group).strip()

    if not text:
        return None

    start = group[0]["start"]
    end = group[-1]["end"]

    return {
        "text": text,
        "start": round(start, 3),
        "end": round(end, 3),
        "duration": round(end - start, 3),
        "fragment_count": len(group),
        "sentence_index": sentence_index,
    }


# =========================================================
# 4. MAIN RECONSTRUCTION PIPELINE
# =========================================================

def reconstruct_sentences(
    fragments,
    boundary_threshold=2,
    max_duration=10.0,
    max_chars=120,
):
    """
    Production-style heuristic sentence reconstruction.
    """

    if not fragments:
        return []


    sentences = []

    current_group = []
    sentence_index = 0

    for i, fragment in enumerate(fragments):

        current_group.append(fragment)

        merged_text = "".join(
            x["text"].strip()
            for x in current_group
        )

        current_start = current_group[0]["start"]
        current_end = current_group[-1]["end"]

        current_duration = current_end - current_start

        # -------------------------------------
        # Calculate gap to next fragment
        # -------------------------------------

        if i < len(fragments) - 1:
            next_frag = fragments[i + 1]

            gap = next_frag["start"] - current_end
            gap = max(gap, 0.0)

        else:
            gap = 999.0  # force flush at end

        # -------------------------------------
        # Compute score
        # -------------------------------------

        score = boundary_score(
            current_text=merged_text,
            gap=gap,
            duration=current_duration,
            max_duration=max_duration,
        )

        # -------------------------------------
        # Hard constraints
        # -------------------------------------

        hard_flush = (
            current_duration >= max_duration
            or len(merged_text) >= max_chars
        )

        # -------------------------------------
        # Flush decision
        # -------------------------------------

        if score >= boundary_threshold or hard_flush:

            sentence = build_sentence(
                current_group,
                sentence_index
            )

            if sentence:
                sentences.append(sentence)
                sentence_index += 1

            current_group = []

    # -----------------------------------------
    # Flush remaining
    # -----------------------------------------

    if current_group:
        sentence = build_sentence(
            current_group,
            sentence_index
        )

        if sentence:
            sentences.append(sentence)

    return sentences

# from captions_helpers import fetch_raw_captions

# fragments=fetch_raw_captions("N1Y4Irsjwpg")[:50]

# sentences=reconstruct_sentences(fragments)

   
# print(fragments)
# print(sentences)
