"""
Japanese YouTube caption reconstruction algorithm.
Converts json3 ASR output into learner-friendly meaning units with accurate timestamps.
"""

import re
import requests
import yt_dlp
import fugashi
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from bisect import bisect_left


# =====================================================================
# Data classes
# =====================================================================

@dataclass
class Token:
    """A sub-segment from YouTube's json3 ASR output."""
    text: str
    start: float
    end: float
    is_event_end: bool = False  # True if this token ends a YouTube event (silence after)


@dataclass
class CharInfo:
    """Per-character timing and structural metadata."""
    start: float
    end: float
    is_event_boundary: bool


@dataclass
class MeaningUnit:
    text: str
    start: float
    end: float
    tokens: List[str] = field(default_factory=list)
    break_reason: Optional[str] = None  # for debugging
    
    def __repr__(self):
        return f"[{self.start:6.2f}s-{self.end:6.2f}s] {self.text}"


# =====================================================================
# Linguistic constants
# =====================================================================

# Hard sentence-ending punctuation
SENTENCE_END_PUNCT = {"。", "．", "！", "？", "!", "?", "…","、"}

# Sentence-final particles (always absorbed into preceding unit)
FINAL_PARTICLES = {"よ", "ね", "な", "ぞ", "ぜ", "わ", "さ", "かな", "かしら"}

# Tokens that signal a clean break AFTER them (subject to validation)
SOFT_BREAK_AFTER = {
    # Copula/polite forms (when truly final)
    "です", "だ", "ます", "ました", "でした", "だった", "ません", "でしょう",
    # Conjunctive particles
     "ので", "けど", "けれど", "けれども", "のに", "ながら",
    # Final particles handled separately above for absorption
}

# Conjunctions that should START a new unit (break BEFORE them)
SOFT_BREAK_BEFORE = {
    "でも", "だから", "それで", "そして", "じゃあ", "じゃ",
    "ところで", "つまり", "ただ", "しかし", "なので", "あと",
    "それから", "それに", "また", "ちなみに", "では",
}

# Particles/forms that must NEVER end a unit (they bind to what follows)
NEVER_END = {
    "は", "が", "を", "に", "で", "へ", "と", "や", "か", "も", "ば",
    "って", "という", "といった", "における", "について",
}

# Surface forms that must NEVER start a unit (orphan signal)
NEVER_START = {
    # Particles
    "は", "が", "を", "に", "で", "へ", "と", "や", "の", "か", "も",
    "から", "まで", "より", "ば", "ても", "でも", "けど", "けれど", "って",
    # Auxiliaries
    "です", "だ", "ます", "ました", "でした", "ない", "ません", "だった",
    "でしょう", "ましょう", "たい", "たかった",
    # Common compound-noun second-halves (extend per domain)
    "評価", "学習", "問題", "結果", "場合", "情報", "内容", "方法",
}

# POS tags that should never end a unit
NEVER_END_POS = {"助詞", "助動詞", "接頭詞", "接続詞"}

# POS tags that should never start a unit
NEVER_START_POS = {"助詞", "助動詞", "接尾辞"}

# Audio gap thresholds (seconds)
STRONG_GAP = 0.6   # definite sentence boundary
MEDIUM_GAP = 0.3   # boundary if unit already long enough

# Length constraints (characters)
MIN_UNIT_LEN = 6
TARGET_UNIT_LEN = 25
MAX_UNIT_LEN = 45
HARD_MAX_LEN = 70  # absolute ceiling, force a break even if not ideal


# =====================================================================
# Step 1: Fetch and parse json3
# =====================================================================

def fetch_tokens(video_id: str, lang: str = "ja") -> List[Token]:
    """
    Fetch YouTube captions in json3 format and convert to sub-segment tokens.
    Each token has audio-grounded start/end times from YouTube's ASR.
    """
    ydl_opts = {"skip_download": True, "quiet": True, "no_warnings": True,"format":None,"extract_flat":False}
#     ydl_opts = {
#     "skip_download": True,
#     "quiet": True,
#     "no_warnings": True,
#     "writesubtitles": True,
#     "writeautomaticsub": True,
#     "subtitleslangs": [lang],
#     "subtitlesformat": "json3",
    
#     # Critical: skip format extraction entirely
#     "extractor_args": {
#         "youtube": {
#             "player_client": ["web"],
#             "skip": ["hls", "dash", "translated_subs"],
#         }
#     },
# }
    url = f"https://www.youtube.com/watch?v={video_id}"
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    
    # Prefer manual subs, fall back to auto-generated
    subs = info.get("subtitles", {}).get(lang) or \
           info.get("automatic_captions", {}).get(lang)
    if not subs:
        raise RuntimeError(f"No {lang} captions available for {video_id}")
    
    json3_entry = next((s for s in subs if s["ext"] == "json3"), None)
    if not json3_entry:
        raise RuntimeError("No json3 format available")
    
    data = requests.get(json3_entry["url"]).json()
    
    tokens = []
    for event in data.get("events", []):
        if "segs" not in event:
            continue
        base_ms = event.get("tStartMs", 0)
        segs = event["segs"]
        
        # Filter out newline-only and empty segments
        real_segs = [
            (i, s) for i, s in enumerate(segs)
            if s.get("utf8", "").strip() and s.get("utf8") != "\n"
        ]
        if not real_segs:
            continue
        
        for idx, (_, seg) in enumerate(real_segs):
            text = seg["utf8"]
            offset_ms = seg.get("tOffsetMs", 0)
            start = (base_ms + offset_ms) / 1000.0
            
            # End time: next segment's offset, or event's end
            if idx + 1 < len(real_segs):
                next_offset = real_segs[idx + 1][1].get("tOffsetMs", offset_ms + 200)
                end = (base_ms + next_offset) / 1000.0
            else:
                duration_ms = event.get("dDurationMs", 300)
                end = (base_ms + duration_ms) / 1000.0
            
            # Sanity: ensure positive duration
            if end <= start:
                end = start + 0.1
            
            is_last_in_event = (idx == len(real_segs) - 1)
            tokens.append(Token(text, start, end, is_event_end=is_last_in_event))
    
    # Sort by start time and dedupe overlapping rolling-caption fragments
    tokens.sort(key=lambda t: t.start)
    return _dedupe_tokens(tokens)


def _dedupe_tokens(tokens: List[Token]) -> List[Token]:
    """Remove overlapping tokens from rolling-caption duplication."""
    if not tokens:
        return tokens
    cleaned = [tokens[0]]
    for tok in tokens[1:]:
        prev = cleaned[-1]
        # If this token starts before previous ends AND has same text, skip
        if tok.start < prev.end and tok.text == prev.text:
            continue
        cleaned.append(tok)
    return cleaned


# =====================================================================
# Step 2: Build text + char-level timing
# =====================================================================

def build_timeline(tokens: List[Token]) -> Tuple[str, List[CharInfo]]:
    """Concatenate tokens into one string with per-character timing."""
    full_text = ""
    char_info: List[CharInfo] = []
    
    for tok in tokens:
        n = len(tok.text)
        if n == 0:
            continue
        duration = max(tok.end - tok.start, 0.05)
        per_char = duration / n
        
        for i in range(n):
            is_boundary = (tok.is_event_end and i == n - 1)
            char_info.append(CharInfo(
                start=tok.start + i * per_char,
                end=tok.start + (i + 1) * per_char,
                is_event_boundary=is_boundary,
            ))
        full_text += tok.text
    
    return full_text, char_info


# =====================================================================
# Step 3: Linguistic helpers
# =====================================================================

TAGGER = fugashi.Tagger()


def _get_pos(mtok) -> str:
    """Safely extract POS1 from a fugashi token."""
    try:
        return mtok.feature.pos1 or ""
    except AttributeError:
        return ""


def _get_pos2(mtok) -> str:
    try:
        return mtok.feature.pos2 or ""
    except AttributeError:
        return ""


def is_compound_noun_continuation(cur_tok, next_tok) -> bool:
    """Would breaking between these split a compound noun?"""
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
    """
    の has multiple uses. Only break after it when it's truly sentence-final.
    """
    if next_tok is None:
        return True
    next_surface = next_tok.surface
    next_pos = _get_pos(next_tok)
    
    if next_surface in SENTENCE_END_PUNCT:
        return True
    if next_surface in FINAL_PARTICLES:
        return False  # absorb instead
    if next_pos == "助詞":
        return False  # nominalizer (のは, のが, etc.)
    if next_pos in {"動詞", "形容詞", "助動詞"}:
        return False  # nominalizer (のだ, のです, etc.)
    return True


def is_safe_to_break_after(cur_tok, next_tok) -> bool:
    """
    Comprehensive check: can we end a unit at cur_tok without orphaning next?
    """
    if next_tok is None:
        return True
    
    cur_surface = cur_tok.surface
    cur_pos = _get_pos(cur_tok)
    next_surface = next_tok.surface
    next_pos = _get_pos(next_tok)
    
    # Current can't end a unit
    if cur_surface in NEVER_END:
        return False
    if cur_pos in NEVER_END_POS and cur_surface not in SOFT_BREAK_AFTER \
       and cur_surface not in FINAL_PARTICLES:
        return False
    
    # Next can't start a unit
    if next_surface in NEVER_START:
        return False
    if next_pos in NEVER_START_POS:
        return False
    
    # Don't split compound nouns
    if is_compound_noun_continuation(cur_tok, next_tok):
        return False
    
    return True


def score_break_point(cur_tok, next_tok) -> float:
    """
    Score how good a break point is. Higher = better. 0 = forbidden.
    Used for finding the best retroactive break when length cap is hit.
    """
    if cur_tok is None:
        return 0
    if not is_safe_to_break_after(cur_tok, next_tok):
        return 0
    
    surface = cur_tok.surface
    pos = _get_pos(cur_tok)
    next_surface = next_tok.surface if next_tok else ""
    
    # Strongest: sentence-end punctuation
    if surface in SENTENCE_END_PUNCT:
        return 10.0
    # Final particle clusters
    if surface in FINAL_PARTICLES and pos == "助詞":
        return 8.5
    # Polite copula/verb endings
    if surface in {"です", "ます", "ました", "でした"}:
        return 8.0
    # Plain copula/verb endings
    if surface in {"だ", "だった", "ない"} and pos in {"助動詞", "形容詞"}:
        return 7.0
    # Conjunctive particles
    if surface in {"から", "ので", "けど", "けれど", "のに"}:
        return 6.5
    # Comma
    if surface in {"、", ","}:
        return 5.0
    # Conjunction starts next
    if next_surface in SOFT_BREAK_BEFORE:
        return 7.0
    # Verb/adjective in terminal form
    try:
        form = cur_tok.feature.form or ""
    except AttributeError:
        form = ""
    if pos == "動詞" and form == "終止形":
        return 4.0
    if pos == "形容詞" and form == "終止形":
        return 4.0
    # Last resort: end of noun phrase before non-noun
    if pos == "名詞" and next_tok and _get_pos(next_tok) not in {"名詞", "接尾辞"}:
        return 2.0
    
    return 0


# =====================================================================
# Step 4: Segmentation
# =====================================================================

def segment_into_units(full_text: str, char_info: List[CharInfo]) -> List[MeaningUnit]:
    if not full_text:
        return []
    
    mecab_tokens = list(TAGGER(full_text))
    if not mecab_tokens:
        return []
    
    units: List[MeaningUnit] = []
    
    cursor = 0  # char position in full_text
    unit_start_char = 0
    unit_token_idx_start = 0  # index into mecab_tokens
    unit_surfaces: List[str] = []
    best_break: Optional[Tuple[int, int, float]] = None  # (mecab_idx, char_end, score)
    
    def emit_unit(end_char: int, end_token_idx: int, reason: str):
        """Emit a unit from current start to end_char and reset state."""
        nonlocal unit_start_char, unit_token_idx_start, unit_surfaces, best_break
        
        text = full_text[unit_start_char:end_char]
        if not text.strip():
            unit_start_char = end_char
            unit_token_idx_start = end_token_idx
            unit_surfaces = []
            best_break = None
            return
        
        start_time = char_info[unit_start_char].start
        end_time = char_info[end_char - 1].end
        
        # Slice surfaces correctly
        surfaces = [mecab_tokens[k].surface for k in range(unit_token_idx_start, end_token_idx)]
        
        units.append(MeaningUnit(
            text=text,
            start=start_time,
            end=end_time,
            tokens=surfaces,
            break_reason=reason,
        ))
        unit_start_char = end_char
        unit_token_idx_start = end_token_idx
        unit_surfaces = []
        best_break = None
    
    i = 0
    while i < len(mecab_tokens):
        mtok = mecab_tokens[i]
        surface = mtok.surface
        pos = _get_pos(mtok)
        
        tok_start_char = cursor
        cursor += len(surface)
        tok_end_char = cursor
        
        unit_surfaces.append(surface)
        unit_len = tok_end_char - unit_start_char
        
        next_tok = mecab_tokens[i + 1] if i + 1 < len(mecab_tokens) else None
        next_surface = next_tok.surface if next_tok else ""
        
        # Audio signals
        last_char_idx = tok_end_char - 1
        is_event_boundary = (
            char_info[last_char_idx].is_event_boundary
            if last_char_idx < len(char_info) else False
        )
        gap_after = 0.0
        if tok_end_char < len(char_info):
            gap_after = char_info[tok_end_char].start - char_info[last_char_idx].end
        
        # Track best break candidate seen in current unit
        score = score_break_point(mtok, next_tok)
        if score > 0 and (best_break is None or score >= best_break[2]):
            best_break = (i, tok_end_char, score)
        
        should_break = False
        reason = None
        
        # ---- Rule 1: Sentence-end punctuation (HARDEST) ----
        if surface in SENTENCE_END_PUNCT and unit_len >= MIN_UNIT_LEN:
            should_break = True
            reason = "punctuation"
        
        # ---- Rule 2: YouTube event boundary (silence detected by ASR) ----
        elif is_event_boundary and unit_len >= MIN_UNIT_LEN \
             and is_safe_to_break_after(mtok, next_tok):
            should_break = True
            reason = "event_boundary"
        
        # ---- Rule 3: Strong audio gap ----
        elif gap_after > STRONG_GAP and unit_len >= MIN_UNIT_LEN \
             and is_safe_to_break_after(mtok, next_tok):
            should_break = True
            reason = "strong_gap"
        
        # ---- Rule 4: Conjunction starts next unit ----
        elif next_surface in SOFT_BREAK_BEFORE and unit_len >= MIN_UNIT_LEN \
             and is_safe_to_break_after(mtok, next_tok):
            should_break = True
            reason = "conj_before"
        
        # ---- Rule 5: Final particle ----
        elif surface in FINAL_PARTICLES and pos == "助詞" \
             and unit_len >= MIN_UNIT_LEN:
            # Absorb additional final particles or punctuation
            if next_surface in FINAL_PARTICLES or next_surface in SENTENCE_END_PUNCT:
                pass  # let next iteration handle the break
            elif is_safe_to_break_after(mtok, next_tok):
                should_break = True
                reason = "final_particle"
        
        # ---- Rule 6: Soft break tokens (です, ます, から, etc.) ----
        elif surface in SOFT_BREAK_AFTER and unit_len >= MIN_UNIT_LEN:
            # Absorb trailing final particles or punctuation
            if next_surface in FINAL_PARTICLES or next_surface in SENTENCE_END_PUNCT:
                pass
            elif is_safe_to_break_after(mtok, next_tok):
                should_break = True
                reason = "soft_after"
        
        # ---- Rule 7: の disambiguation ----
        elif surface == "の" and pos == "助詞" and unit_len >= MIN_UNIT_LEN:
            if is_breakable_no(mtok, next_tok) and is_safe_to_break_after(mtok, next_tok):
                if next_surface not in FINAL_PARTICLES and next_surface not in SENTENCE_END_PUNCT:
                    should_break = True
                    reason = "no_final"
        
        # ---- Rule 8: Medium gap when already past target length ----
        elif gap_after > MEDIUM_GAP and unit_len >= TARGET_UNIT_LEN \
             and is_safe_to_break_after(mtok, next_tok):
            should_break = True
            reason = "medium_gap_long"
        
        # ---- Rule 9: Soft length cap — use best break we've seen ----
        elif unit_len >= MAX_UNIT_LEN:
            if best_break is not None:
                # Retroactively break at the best earlier point
                bk_idx, bk_char, _ = best_break
                emit_unit(bk_char, bk_idx + 1, "max_length_retro")
                # Restart cursor from after the break
                cursor = bk_char
                unit_surfaces = []
                # Re-process remaining tokens starting from bk_idx + 1
                i = bk_idx + 1
                continue
            elif is_safe_to_break_after(mtok, next_tok):
                should_break = True
                reason = "max_length"
        
        # ---- Rule 10: Hard ceiling — force break at first safe spot ----
        elif unit_len >= HARD_MAX_LEN:
            # Walk forward to find ANY safe break, even mediocre
            if is_safe_to_break_after(mtok, next_tok):
                should_break = True
                reason = "hard_max"
        
        if should_break:
            emit_unit(tok_end_char, i + 1, reason)
        
        i += 1
    
    # Flush remainder
    if unit_start_char < len(full_text):
        emit_unit(len(full_text), len(mecab_tokens), "flush")
    
    return units


# =====================================================================
# Step 5: Snap timestamps to real ASR boundaries
# =====================================================================

def snap_and_pad(units: List[MeaningUnit], tokens: List[Token],
                 lead_in: float = 0.08, lead_out: float = 0.12) -> List[MeaningUnit]:
    """
    Replace interpolated times with nearest real YouTube token boundary.
    Validate every output to ensure end > start.
    """
    starts = sorted({t.start for t in tokens})
    ends = sorted({t.end for t in tokens})
    
    def nearest(value: float, candidates: List[float], max_drift: float = 0.3) -> float:
        if not candidates:
            return value
        idx = bisect_left(candidates, value)
        # Compare neighbors
        best = value
        best_diff = max_drift
        for j in (idx - 1, idx):
            if 0 <= j < len(candidates):
                diff = abs(candidates[j] - value)
                if diff < best_diff:
                    best_diff = diff
                    best = candidates[j]
        return best
    
    snapped = []
    for u in units:
        new_start = max(0.0, nearest(u.start, starts) - lead_in)
        new_end = nearest(u.end, ends) + lead_out
        
        # Critical: validate ordering
        if new_end <= new_start:
            # Snapping broke the range — fall back to original
            new_start = u.start
            new_end = u.end
        
        if new_end <= new_start:
            # Still broken — force minimum duration
            new_end = new_start + 0.3
        
        snapped.append(MeaningUnit(
            text=u.text, start=new_start, end=new_end,
            tokens=u.tokens, break_reason=u.break_reason,
        ))
    
    # Resolve overlaps between consecutive units
    for i in range(len(snapped) - 1):
        if snapped[i].end > snapped[i + 1].start:
            mid = (snapped[i].end + snapped[i + 1].start) / 2
            # Only apply if it doesn't break either unit's ordering
            if mid > snapped[i].start and mid < snapped[i + 1].end:
                snapped[i].end = mid
                snapped[i + 1].start = mid
            else:
                # Hard case: force a sensible boundary
                snapped[i + 1].start = snapped[i].end + 0.01
    
    return snapped


# =====================================================================
# Step 6: Post-process for learner quality
# =====================================================================

# Filler-only patterns
FILLER_ONLY = re.compile(
    r'^[。、！？!?\s]*'
    r'(はい|うん|ええ|まあ|あの|その|えー|えっと|なんか|ね|よ)?'
    r'[。、！？!?\s]*$'
)


def post_process(units: List[MeaningUnit]) -> List[MeaningUnit]:
    """
    Merge orphan units, filler-only fragments, and units that start/end
    with stranded particles.
    """
    if not units:
        return units
    
    merged: List[MeaningUnit] = [units[0]]
    
    for u in units[1:]:
        prev = merged[-1]
        should_merge = False
        
        # 1. Current unit is too short
        if len(u.text) < MIN_UNIT_LEN:
            should_merge = True
        
        # 2. Current unit starts with a particle/auxiliary (orphan)
        elif u.text and u.text[0] in NEVER_START:
            should_merge = True
        
        # 3. Current unit is just filler + punctuation
        elif FILLER_ONLY.match(u.text):
            should_merge = True
        
        # 4. Previous unit ended with a NEVER_END character
        elif prev.text and prev.text[-1] in {"は", "が", "を", "に", "で", "へ", "と", "や"}:
            should_merge = True
        
        # 5. Previous unit was very short and current is normal length
        elif len(prev.text) < MIN_UNIT_LEN:
            should_merge = True
        
        # Don't merge if combined would exceed hard ceiling
        if should_merge and (len(prev.text) + len(u.text)) > HARD_MAX_LEN:
            should_merge = False
        
        if should_merge:
            merged[-1] = MeaningUnit(
                text=prev.text + u.text,
                start=prev.start,
                end=u.end,
                tokens=prev.tokens + u.tokens,
                break_reason=f"merged({prev.break_reason}+{u.break_reason})",
            )
        else:
            merged.append(u)
    
    # Final validation pass: ensure all timestamps are valid
    for u in merged:
        if u.end <= u.start:
            u.end = u.start + 0.3
    
    return merged


# =====================================================================
# Driver
# =====================================================================

def reconstruct(video_id: str, lang: str = "ja",
                target_unit_len: Optional[int] = None,
                max_unit_len: Optional[int] = None) -> List[dict]:
    """
    Main entry point. Reconstruct YouTube captions into learner-friendly meaning units.
    
    Args:
        video_id: YouTube video ID
        lang: Caption language (default: ja)
        target_unit_len: Override TARGET_UNIT_LEN (e.g., 18 for beginners, 35 for advanced)
        max_unit_len: Override MAX_UNIT_LEN
    
    Returns:
        List of MeaningUnit objects with audio-grounded timestamps.
    """
    global TARGET_UNIT_LEN, MAX_UNIT_LEN
    
    # Optional per-call tuning
    saved_target, saved_max = TARGET_UNIT_LEN, MAX_UNIT_LEN
    if target_unit_len is not None:
        TARGET_UNIT_LEN = target_unit_len
    if max_unit_len is not None:
        MAX_UNIT_LEN = max_unit_len
    
    try:
        tokens = fetch_tokens(video_id, lang)
        full_text, char_info = build_timeline(tokens)
        units = segment_into_units(full_text, char_info)
        units = snap_and_pad(units, tokens)
        units = post_process(units)
        return units
    finally:
        TARGET_UNIT_LEN, MAX_UNIT_LEN = saved_target, saved_max

def to_dict(unit: MeaningUnit, sentence_index: int) -> dict:
    return {
        "text": unit.text,
        "start": round(unit.start, 3),
        "end": round(unit.end, 3),
        "duration": round(unit.end - unit.start, 3),
        "sentence_index": sentence_index,
    }
    
def reconstruct_as_dicts(video_id: str, lang: str = "ja", **kwargs) -> List[dict]:
    """Public API: returns list of dicts in the application's expected format."""
    units = reconstruct(video_id, lang, **kwargs)
    return [to_dict(u, idx) for idx, u in enumerate(units)]
# =====================================================================
# Quick test harness
# =====================================================================

# if __name__ == "__main__":
#     import sys
    
#     video_id = sys.argv[1] if len(sys.argv) > 1 else "4HnvdX8dl-Y"
    
#     print(f"Reconstructing video: {video_id}\n")
#     units = reconstruct(video_id)
    
#     for u in units:
#         print(u)
    
#     print(f"\nTotal: {len(units)} meaning units")
    
#     # Summary of break reasons (useful for debugging)
#     from collections import Counter
#     reasons = Counter(u.break_reason for u in units)
#     print("\nBreak reasons:")
#     for reason, count in reasons.most_common():
#         print(f"  {reason}: {count}")