from youtube_transcript_api import YouTubeTranscriptApi
from fugashi import Tagger
from copy import deepcopy
import html
import requests
import re
import yt_dlp

ytt_api=YouTubeTranscriptApi()
tagger = Tagger()

def fetch_raw_captions_deprecated(video_id:str):
    snippets= ytt_api.fetch(video_id,languages=("ja",)).snippets
    return [{"index":i,"text":snippet.text,"start":snippet.start,"duration":snippet.duration} for i,snippet in enumerate(snippets)]

def fetch_raw_captions(video_id: str, lang: str = "ja") -> list[dict]:
    """
    Line-level captions matching youtube-transcript-api's output format.
    Uses yt-dlp + json3 for resilience against IP bans.
    """
    # ydl_opts = {
    #     "skip_download": True,
    #     "quiet": True,
    #     "no_warnings": True,
    #     "writesubtitles": True,
    #     "writeautomaticsub": True,
    #     "subtitleslangs": [lang],
    #     "subtitlesformat": "json3",
    #     "extractor_args": {
    #         "youtube": {
    #             "player_client": ["web"],
    #             "skip": ["hls", "dash", "translated_subs"],
    #         }
    #     },
    # }
    ydl_opts = {"skip_download": True, "quiet": True, "no_warnings": True,"format":None,"extract_flat":False}

    url = f"https://www.youtube.com/watch?v={video_id}"
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    
    subs = info.get("subtitles", {}).get(lang) or \
           info.get("automatic_captions", {}).get(lang)
    if not subs:
        raise RuntimeError(f"No {lang} captions available for {video_id}")
    
    json3_entry = next((s for s in subs if s["ext"] == "json3"), None)
    if not json3_entry:
        raise RuntimeError("No json3 format available")
    
    data = requests.get(json3_entry["url"]).json()
    
    snippets = []
    index = 0
    
    for event in data.get("events", []):
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
        
        snippets.append({
            "index": index,
            "text": text,
            "start": round(event.get("tStartMs", 0) / 1000.0, 3),
            "duration": round(event.get("dDurationMs", 0) / 1000.0, 3),
        })
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
        
        if current_text.startswith(prev["text"]) and len(current_text) > len(prev["text"]):
            cleaned[-1] = snippet
        elif prev["text"].startswith(current_text):
            continue
        else:
            cleaned.append(snippet)
    
    return cleaned

# raw_captions=fetch_raw_captions("vZmCtYoIRLU")


# text = "麩菓子は、麩を主材料とした日本の菓子。"
# tagger.parse(text)
# # => '麩 菓子 は 、 麩 を 主材 料 と し た 日本 の 菓子 。'
# for word in tagger(text):
#     print(word.surface, word.feature.lemma, word.pos, sep='\t')
#     # "feature" is the Unidic feature data as a named tuple

def analyse_token(text):
    tokens = []
    node_list = tagger.parseToNodeList(text)
    
    for node in node_list:
        if node.surface and node.surface.strip():
            token_features = node.feature
            is_content_token=is_content_word(token_features)
            token_base_form=token_features.lemma if  token_features.lemma != '*' else node.surface
            token_pos=token_features.pos1
            token_pos_detail=token_features.pos2
            tokens.append({
                'surface': node.surface,
                'base_form':token_base_form,
                'pos': token_pos,          # Part of speech
                'pos_detail': token_pos_detail,   # POS subcategory
                'is_content_word':is_content_token,
            })
    
    return tokens


def tokenize_captions(raw_captions:list[dict]):
    tokenized_captions=raw_captions
    for caption in tokenized_captions:
        caption["tokens"]=analyse_token(caption['text'])
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

CONTENT_POS = {'名詞', '動詞', '形容詞', '形容動詞', '副詞'}
EXCLUDE_POS_DETAIL = {'非自立', '代名詞', '数'}

def is_content_word(token_features):
    token_base_form=token_features.lemma if  token_features.lemma != '*' else None
    token_pos=token_features.pos1
    token_pos_detail=token_features.pos2
    if token_pos not in CONTENT_POS:
        return False
    if token_pos_detail in EXCLUDE_POS_DETAIL:
        return False
    if not token_base_form or len(token_base_form) < 2:
        return False
    return True


def process_captions(raw_captions:list[dict])->list[dict]:
    normalized_captions=normalize_captions_fragments(raw_captions)
    return tokenize_captions(normalized_captions)

# print(tokenize_captions(fetch_raw_captions("j16G26S-18A"))[2])
# print(process_captions(fetch_raw_captions("j16G26S-18A"))[1])