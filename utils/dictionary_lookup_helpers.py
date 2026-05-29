import json
import os
import re
from collections import defaultdict
from functools import lru_cache

from cutlet import Cutlet
from fugashi import Tagger

from services.google_translate_service import fall_back_google_translate

LEMMA_NORMALIZE = {
    "為る": "する",
    "居る": "いる",
    "有る": "ある",
    "成る": "なる",
    "出来る": "できる",
    "良い": "いい",
    "無い": "ない",
}

converter = Cutlet()


@lru_cache(maxsize=1)
def _load_index() -> tuple[dict, dict]:
    path = os.path.join(
        os.path.dirname(__file__), "data", "jmdictExtended-2026-05-26.json"
    )
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    index = {}
    jlpt_index = {}
    for word in data["words"]:
        jlpt_level = None
        # Index by kanji forms
        for k in word.get("kanji", []):
            index.setdefault(k["text"], word)
            level = k.get("jlptLevel")
            if level:
                jlpt_level = level
        # Index by kana forms
        for k in word.get("kana", []):
            index.setdefault(k["text"], word)
            level = k.get("jlptLevel")
            if level:
                jlpt_level = level

        if jlpt_level:
            tier = f"N{jlpt_level}"
            for k in word.get("kanji", []):
                jlpt_index[k["text"]] = tier
            for k in word.get("kana", []):
                jlpt_index[k["text"]] = tier

    return index, jlpt_index


def get_jlpt_tier(base_form: str) -> str:
    _, jlpt_index = _load_index()

    tier = jlpt_index.get(base_form)
    if tier:
        return tier

    normalised = LEMMA_NORMALIZE.get(base_form)
    if normalised:
        return jlpt_index.get(normalised, "UNKNOWN")

    return "UNKNOWN"


def normalize_pos_simple(pos_list: list[str]) -> str:
    pos_set = set(pos_list)

    # Verb (covers v*, aux-v)
    if any(p.startswith("v") for p in pos_set) or "aux-v" in pos_set:
        return "verb"

    # Adjective
    if any(p.startswith("adj") for p in pos_set):
        return "adjective"

    # Adverb
    if "adv" in pos_set:
        return "adverb"

    # Noun
    if "n" in pos_set or any(p.startswith("n-") for p in pos_set):
        return "noun"

    # Others (optional but useful)
    if "pn" in pos_set:
        return "pronoun"
    if "prt" in pos_set:
        return "particle"
    if "conj" in pos_set:
        return "conjunction"
    if "int" in pos_set:
        return "interjection"

    return "other"


def extract_group_meanings(senses: list[dict], max_pos=3, max_gloss_per_pos=3):
    grouped = defaultdict(list)

    for sense in senses:
        normalized_pos = normalize_pos_simple(sense.get("partOfSpeech", []))

        for g in sense.get("gloss", []):
            if g.get("lang") == "eng":
                grouped[normalized_pos].append(g["text"])

    results = []
    for pos, meanings in list(grouped.items())[:max_pos]:
        results.append({"pos": pos, "meanings": meanings[:max_gloss_per_pos]})

    return results


def lookup_word_full(token: tuple) -> dict:
    surface_form = token[0]
    base_form = token[1]
    if not is_japanese(surface_form):
        return {
            "meanings": [{"pos": None, "meanings": None}],
            "romanji_reading": None,
            "jlpt_tier": "UNKNOWN",
            "found": False,
        }
    index = _load_index()[0]
    meanings = []
    reading = surface_form

    surface_form_entry = index.get(surface_form)
    if surface_form_entry:
        print("Surface Form Found!")
        senses = surface_form_entry.get("sense", [])
        meanings = extract_group_meanings(senses)
        kana_forms = surface_form_entry.get("kana", [])
        if kana_forms:
            reading = kana_forms[0]["text"]
    else:
        print(f"Base Form Trying..{base_form}")
        base_form_entry = index.get(base_form)
        print(f"Base:{base_form_entry}")
        if base_form_entry:
            senses = base_form_entry.get("sense", [])
            meanings = extract_group_meanings(senses)
            kana_forms = base_form_entry.get("kana", [])
            if kana_forms:
                reading = kana_forms[0]["text"]

    if not meanings or not any(m["meanings"] for m in meanings):
        print("No meaning! GCT trying..")
        meanings = [
            {
                "pos": "web_translate",
                "meanings": fall_back_google_translate(surface_form),
            }
        ]

    romanji_reading = kana_to_romanji(reading)
    jlpt_tier = get_jlpt_tier(base_form)

    return {
        "meanings": meanings,
        "romanji_reading": romanji_reading,
        "jlpt_tier": jlpt_tier,
        "found": True,
    }


def kana_to_romanji(kana: str):
    """
    return romanji pronunciation reading

    """
    romaji_reading = converter.romaji(text=kana, capitalize=False)

    return romaji_reading


def is_japanese(text):
    return re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", text) is not None


# print(lookup_word_full("歌っ"))
