"""
Japanese sentence reconstruction from a Whisper transcript.

Key difference from the json3 version: timing is audio-grounded.
Whisper (with word_timestamps=True) gives a real start/end per word, so:
  - unit boundaries snap to real word boundaries (no per-char interpolation),
  - gap detection reads true inter-word silences (a trustworthy break signal),
  - the old snap_and_pad + fixed-padding hacks are gone.

The linguistic segmentation logic (break scoring, particle/POS guards,
compound-noun protection, の disambiguation, orphan merging) is carried over
unchanged — it operates on fugashi tokens of the text and doesn't care where
the text came from.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import fugashi

# =====================================================================
# Data classes
# =====================================================================


@dataclass
class WhisperWord:
    """One word from Whisper with audio-grounded timing."""

    text: str
    start: float
    end: float
    is_segment_end: bool = False  # last word of a Whisper segment (soft boundary hint)


@dataclass
class MeaningUnit:
    text: str
    start: float
    end: float
    tokens: List[str] = field(default_factory=list)
    break_reason: Optional[str] = None

    def __repr__(self):
        return f"[{self.start:6.2f}s-{self.end:6.2f}s] {self.text}"


# =====================================================================
# Linguistic constants  (unchanged from the original)
# =====================================================================

SENTENCE_END_PUNCT = {"。", "．", "！", "？", "!", "?", "…", "、"}
FINAL_PARTICLES = {"よ", "ね", "な", "ぞ", "ぜ", "わ", "さ", "かな", "かしら"}

SOFT_BREAK_AFTER = {
    "です",
    "だ",
    "ます",
    "ました",
    "でした",
    "だった",
    "ません",
    "でしょう",
    "ので",
    "けど",
    "けれど",
    "けれども",
    "のに",
    "ながら",
}
SOFT_BREAK_BEFORE = {
    "でも",
    "だから",
    "それで",
    "そして",
    "じゃあ",
    "じゃ",
    "ところで",
    "つまり",
    "ただ",
    "しかし",
    "なので",
    "あと",
    "それから",
    "それに",
    "また",
    "ちなみに",
    "では",
}
NEVER_END = {
    "は",
    "が",
    "を",
    "に",
    "で",
    "へ",
    "と",
    "や",
    "か",
    "も",
    "ば",
    "って",
    "という",
    "といった",
    "における",
    "について",
}
NEVER_START = {
    "は",
    "が",
    "を",
    "に",
    "で",
    "へ",
    "と",
    "や",
    "の",
    "か",
    "も",
    "から",
    "まで",
    "より",
    "ば",
    "ても",
    "でも",
    "けど",
    "けれど",
    "って",
    "です",
    "だ",
    "ます",
    "ました",
    "でした",
    "ない",
    "ません",
    "だった",
    "でしょう",
    "ましょう",
    "たい",
    "たかった",
    "評価",
    "学習",
    "問題",
    "結果",
    "場合",
    "情報",
    "内容",
    "方法",
}
NEVER_END_POS = {"助詞", "助動詞", "接頭詞", "接続詞"}
NEVER_START_POS = {"助詞", "助動詞", "接尾辞"}

# Audio gap thresholds (seconds) — now reading REAL silences, so these are trustworthy.
STRONG_GAP = 0.45  # a genuine pause → sentence boundary
MEDIUM_GAP = 0.25  # boundary if unit already long enough

MIN_UNIT_LEN = 6
TARGET_UNIT_LEN = 25
MAX_UNIT_LEN = 45
HARD_MAX_LEN = 70


# =====================================================================
# Step 1: Whisper -> WhisperWord list  (the new input adapter)
# =====================================================================


def words_from_whisper(segments) -> List[WhisperWord]:
    """
    Convert faster-whisper segments (transcribed with word_timestamps=True)
    into a flat, time-ordered list of WhisperWord.

    `segments` is the iterable returned by:
        segments, _ = model.transcribe(audio, language="ja", word_timestamps=True)
    Pass list(segments) if you need to reuse it.
    """
    words: List[WhisperWord] = []
    for seg in segments:
        seg_words = getattr(seg, "words", None)
        if seg_words:
            n = len(seg_words)
            for j, w in enumerate(seg_words):
                text = (w.word or "").strip()  # Japanese has no spaces; strip is safe
                if not text:
                    continue
                start = w.start if w.start is not None else seg.start
                end = w.end if w.end is not None else seg.end
                if end <= start:
                    end = start + 0.05
                words.append(WhisperWord(text, start, end, is_segment_end=(j == n - 1)))
        else:
            # Fallback: no word timings on this segment — treat whole segment as one word.
            text = (seg.text or "").strip()
            if text:
                words.append(WhisperWord(text, seg.start, seg.end, is_segment_end=True))

    # Guard against any out-of-order timing from Whisper.
    words.sort(key=lambda w: w.start)
    return words


# =====================================================================
# Step 2: Build text + char->word index map
# =====================================================================


def build_char_timeline(words: List[WhisperWord]) -> Tuple[str, List[int]]:
    """
    Concatenate word text into one string and record, for each character,
    the index of the Whisper word it belongs to. That index is how any
    character position is resolved back to a REAL audio time later.
    """
    full_text = ""
    char_word_idx: List[int] = []
    for wi, w in enumerate(words):
        for _ in w.text:
            char_word_idx.append(wi)
        full_text += w.text
    return full_text, char_word_idx


# =====================================================================
# Step 3: Linguistic helpers  (unchanged from the original)
# =====================================================================

TAGGER = fugashi.Tagger()


def _get_pos(mtok) -> str:
    try:
        return mtok.feature.pos1 or ""
    except AttributeError:
        return ""


def is_compound_noun_continuation(cur_tok, next_tok) -> bool:
    if next_tok is None:
        return False
    cur_pos = _get_pos(cur_tok)
    next_pos = _get_pos(next_tok)
    if cur_pos == "名詞" and next_pos == "名詞":
        return True
    if cur_pos == "接頭詞" and next_pos == "名詞":
        return True
    if cur_pos == "名詞" and next_pos == "接尾辞":
        return True
    return False


def is_breakable_no(cur_tok, next_tok) -> bool:
    if next_tok is None:
        return True
    next_surface = next_tok.surface
    next_pos = _get_pos(next_tok)
    if next_surface in SENTENCE_END_PUNCT:
        return True
    if next_surface in FINAL_PARTICLES:
        return False
    if next_pos == "助詞":
        return False
    if next_pos in {"動詞", "形容詞", "助動詞"}:
        return False
    return True


def is_safe_to_break_after(cur_tok, next_tok) -> bool:
    if next_tok is None:
        return True
    cur_surface = cur_tok.surface
    cur_pos = _get_pos(cur_tok)
    next_surface = next_tok.surface
    next_pos = _get_pos(next_tok)
    if cur_surface in NEVER_END:
        return False
    if (
        cur_pos in NEVER_END_POS
        and cur_surface not in SOFT_BREAK_AFTER
        and cur_surface not in FINAL_PARTICLES
    ):
        return False
    if next_surface in NEVER_START:
        return False
    if next_pos in NEVER_START_POS:
        return False
    if is_compound_noun_continuation(cur_tok, next_tok):
        return False
    return True


def score_break_point(cur_tok, next_tok) -> float:
    if cur_tok is None:
        return 0
    if not is_safe_to_break_after(cur_tok, next_tok):
        return 0
    surface = cur_tok.surface
    pos = _get_pos(cur_tok)
    next_surface = next_tok.surface if next_tok else ""
    if surface in SENTENCE_END_PUNCT:
        return 10.0
    if surface in FINAL_PARTICLES and pos == "助詞":
        return 8.5
    if surface in {"です", "ます", "ました", "でした"}:
        return 8.0
    if surface in {"だ", "だった", "ない"} and pos in {"助動詞", "形容詞"}:
        return 7.0
    if surface in {"から", "ので", "けど", "けれど", "のに"}:
        return 6.5
    if surface in {"、", ","}:
        return 5.0
    if next_surface in SOFT_BREAK_BEFORE:
        return 7.0
    try:
        form = cur_tok.feature.form or ""
    except AttributeError:
        form = ""
    if pos == "動詞" and form == "終止形":
        return 4.0
    if pos == "形容詞" and form == "終止形":
        return 4.0
    if pos == "名詞" and next_tok and _get_pos(next_tok) not in {"名詞", "接尾辞"}:
        return 2.0
    return 0


# =====================================================================
# Step 4: Segmentation  (audio signals now come from real word times)
# =====================================================================


def segment_into_units(
    full_text: str, words: List[WhisperWord], char_word_idx: List[int]
) -> List[MeaningUnit]:
    if not full_text:
        return []
    mecab_tokens = list(TAGGER(full_text))
    if not mecab_tokens:
        return []

    units: List[MeaningUnit] = []
    cursor = 0
    unit_start_char = 0
    unit_token_idx_start = 0
    best_break: Optional[Tuple[int, int, float]] = None  # (mecab_idx, char_end, score)

    def emit_unit(end_char: int, end_token_idx: int, reason: str):
        nonlocal unit_start_char, unit_token_idx_start, best_break
        text = full_text[unit_start_char:end_char]
        if not text.strip():
            unit_start_char = end_char
            unit_token_idx_start = end_token_idx
            best_break = None
            return
        # --- TIMING: snap to real Whisper word boundaries ---
        first_word = char_word_idx[unit_start_char]
        last_word = char_word_idx[end_char - 1]
        start_time = words[first_word].start
        end_time = words[last_word].end
        surfaces = [
            mecab_tokens[k].surface for k in range(unit_token_idx_start, end_token_idx)
        ]
        units.append(
            MeaningUnit(
                text=text,
                start=start_time,
                end=end_time,
                tokens=surfaces,
                break_reason=reason,
            )
        )
        unit_start_char = end_char
        unit_token_idx_start = end_token_idx
        best_break = None

    i = 0
    while i < len(mecab_tokens):
        mtok = mecab_tokens[i]
        surface = mtok.surface
        pos = _get_pos(mtok)

        cursor += len(surface)
        tok_end_char = cursor
        unit_len = tok_end_char - unit_start_char

        next_tok = mecab_tokens[i + 1] if i + 1 < len(mecab_tokens) else None
        next_surface = next_tok.surface if next_tok else ""

        # --- Audio signals from REAL word timing ---
        last_char_idx = tok_end_char - 1
        cur_word = char_word_idx[last_char_idx]
        at_word_boundary = (tok_end_char >= len(full_text)) or (
            char_word_idx[tok_end_char] != cur_word
        )
        gap_after = 0.0
        is_segment_end = False
        if at_word_boundary:
            is_segment_end = words[cur_word].is_segment_end
            if tok_end_char < len(full_text):
                next_word = char_word_idx[tok_end_char]
                gap_after = max(0.0, words[next_word].start - words[cur_word].end)

        score = score_break_point(mtok, next_tok)
        if score > 0 and (best_break is None or score >= best_break[2]):
            best_break = (i, tok_end_char, score)

        should_break = False
        reason = None

        if surface in SENTENCE_END_PUNCT and unit_len >= MIN_UNIT_LEN:
            should_break, reason = True, "punctuation"
        elif (
            is_segment_end
            and unit_len >= MIN_UNIT_LEN
            and is_safe_to_break_after(mtok, next_tok)
        ):
            should_break, reason = True, "segment_end"
        elif (
            gap_after > STRONG_GAP
            and unit_len >= MIN_UNIT_LEN
            and is_safe_to_break_after(mtok, next_tok)
        ):
            should_break, reason = True, "strong_gap"
        elif (
            next_surface in SOFT_BREAK_BEFORE
            and unit_len >= MIN_UNIT_LEN
            and is_safe_to_break_after(mtok, next_tok)
        ):
            should_break, reason = True, "conj_before"
        elif surface in FINAL_PARTICLES and pos == "助詞" and unit_len >= MIN_UNIT_LEN:
            if next_surface in FINAL_PARTICLES or next_surface in SENTENCE_END_PUNCT:
                pass
            elif is_safe_to_break_after(mtok, next_tok):
                should_break, reason = True, "final_particle"
        elif surface in SOFT_BREAK_AFTER and unit_len >= MIN_UNIT_LEN:
            if next_surface in FINAL_PARTICLES or next_surface in SENTENCE_END_PUNCT:
                pass
            elif is_safe_to_break_after(mtok, next_tok):
                should_break, reason = True, "soft_after"
        elif surface == "の" and pos == "助詞" and unit_len >= MIN_UNIT_LEN:
            if is_breakable_no(mtok, next_tok) and is_safe_to_break_after(
                mtok, next_tok
            ):
                if (
                    next_surface not in FINAL_PARTICLES
                    and next_surface not in SENTENCE_END_PUNCT
                ):
                    should_break, reason = True, "no_final"
        elif (
            gap_after > MEDIUM_GAP
            and unit_len >= TARGET_UNIT_LEN
            and is_safe_to_break_after(mtok, next_tok)
        ):
            should_break, reason = True, "medium_gap_long"
        elif unit_len >= MAX_UNIT_LEN:
            if best_break is not None:
                bk_idx, bk_char, _ = best_break
                emit_unit(bk_char, bk_idx + 1, "max_length_retro")
                cursor = bk_char
                i = bk_idx + 1
                continue
            elif is_safe_to_break_after(mtok, next_tok):
                should_break, reason = True, "max_length"
        elif unit_len >= HARD_MAX_LEN:
            if is_safe_to_break_after(mtok, next_tok):
                should_break, reason = True, "hard_max"

        if should_break:
            emit_unit(tok_end_char, i + 1, reason)

        i += 1

    if unit_start_char < len(full_text):
        emit_unit(len(full_text), len(mecab_tokens), "flush")

    return units


# =====================================================================
# Step 5: Post-process  (unchanged logic; times stay word-grounded)
# =====================================================================

FILLER_ONLY = re.compile(
    r"^[。、！？!?\s]*"
    r"(はい|うん|ええ|まあ|あの|その|えー|えっと|なんか|ね|よ)?"
    r"[。、！？!?\s]*$"
)


def post_process(units: List[MeaningUnit]) -> List[MeaningUnit]:
    if not units:
        return units
    merged: List[MeaningUnit] = [units[0]]
    for u in units[1:]:
        prev = merged[-1]
        should_merge = False
        if len(u.text) < MIN_UNIT_LEN:
            should_merge = True
        elif u.text and u.text[0] in NEVER_START:
            should_merge = True
        elif FILLER_ONLY.match(u.text):
            should_merge = True
        elif prev.text and prev.text[-1] in {
            "は",
            "が",
            "を",
            "に",
            "で",
            "へ",
            "と",
            "や",
        }:
            should_merge = True
        elif len(prev.text) < MIN_UNIT_LEN:
            should_merge = True
        if should_merge and (len(prev.text) + len(u.text)) > HARD_MAX_LEN:
            should_merge = False
        if should_merge:
            merged[-1] = MeaningUnit(
                text=prev.text + u.text,
                start=prev.start,  # real word start of the first unit
                end=u.end,  # real word end of the merged-in unit
                tokens=prev.tokens + u.tokens,
                break_reason=f"merged({prev.break_reason}+{u.break_reason})",
            )
        else:
            merged.append(u)
    return merged


def resolve_overlaps(units: List[MeaningUnit]) -> List[MeaningUnit]:
    """If a mid-word break made two units share a word, split the boundary."""
    for i in range(len(units) - 1):
        if units[i].end > units[i + 1].start:
            mid = (units[i].end + units[i + 1].start) / 2
            units[i].end = mid
            units[i + 1].start = mid
    for u in units:
        if u.end <= u.start:
            u.end = u.start + 0.3
    return units


def apply_shadow_padding(
    units: List[MeaningUnit], lead_in: float = 0.25, lead_out: float = -0.09
) -> List[MeaningUnit]:
    """
    Optional small comfort margin for the shadowing path. Because timing is
    already word-accurate, this is a tiny cushion (err slightly long), not the
    correction-for-bad-data that the old json3 padding had to be.
    """
    for idx, u in enumerate(units):
        u.start = max(0.0, u.start - lead_in)
        u.end = u.end + lead_out
        if idx + 1 < len(units) and u.end > units[idx + 1].start:
            u.end = units[idx + 1].start
    return units


# =====================================================================
# Driver
# =====================================================================


def reconstruct_from_whisper(segments, shadow: bool = False) -> List[MeaningUnit]:
    """
    Main entry point. `segments` = faster-whisper output with word_timestamps=True.
    Set shadow=True to add the small lead-in/out cushion for the shadowing path.
    """
    words = words_from_whisper(segments)
    if not words:
        return []
    full_text, char_word_idx = build_char_timeline(words)
    units = segment_into_units(full_text, words, char_word_idx)
    units = post_process(units)
    units = resolve_overlaps(units)
    if shadow:
        units = apply_shadow_padding(units)
    return units


def to_dict(unit: MeaningUnit, sentence_index: int) -> dict:
    return {
        "text": unit.text,
        "start": round(unit.start, 3),
        "end": round(unit.end, 3),
        "duration": round(unit.end - unit.start, 3),
        "sentence_index": sentence_index,
    }


def reconstruct_sentences_from_whisper(segments, shadow: bool = False) -> List[dict]:
    """Public API: list of dicts in the application's expected format."""
    units = reconstruct_from_whisper(segments, shadow=shadow)
    return [to_dict(u, idx) for idx, u in enumerate(units)]


def reconstruct_sentence_for_manual(captions: list[dict]) -> List[dict]:
    return [
        {
            "text": caption["text"],
            "start": round(caption["start"], 3),
            "end": round(caption["end"], 3),
            "duration": round(caption["duration"], 3),
            "sentence_index": caption["index"],
        }
        for caption in captions
    ]
