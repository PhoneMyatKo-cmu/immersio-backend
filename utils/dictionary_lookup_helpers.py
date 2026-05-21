from collections import defaultdict
import json
import os
from functools import lru_cache
from fugashi import Tagger
from cutlet import Cutlet
from google.cloud import translate
from pathlib import Path


converter=Cutlet()

@lru_cache(maxsize=1)
def _load_index() -> dict:
    path = os.path.join(
        os.path.dirname(__file__),
        "data",
        "jmdict-eng-3.6.2.json"
    )
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    index = {}
    for word in data["words"]:
        # Index by kanji forms
        for k in word.get("kanji", []):
            index.setdefault(k["text"], word)
        # Index by kana forms
        for k in word.get("kana", []):
            index.setdefault(k["text"], word)

    return index

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

def extract_group_meanings(senses:list[dict],max_pos=3,max_gloss_per_pos=3):
    grouped = defaultdict(list)

    for sense in senses:
        normalized_pos = normalize_pos_simple(sense.get("partOfSpeech", []))

        for g in sense.get("gloss", []):
            if g.get("lang") == "eng":
                grouped[normalized_pos].append(g["text"])

    results = []
    for pos, meanings in list(grouped.items())[:max_pos]:
        results.append({
            "pos": pos,
            "meanings": meanings[:max_gloss_per_pos]
        })

    return results


def lookup_word_full(surface_form: str) -> dict:
    
    if not is_japanese(surface_form):
        return {"meanings":[{"pos":None,"meanings":None}],
                "romanji_reading":None,
                "found":False}
    index = _load_index()
    entry = index.get(surface_form)

    meanings=[]
    reading = surface_form
    if entry:
        senses=entry.get("sense",[])
        meanings= extract_group_meanings(senses)
        kana_forms = entry.get("kana", [])
        if kana_forms:
            reading = kana_forms[0]["text"]
    

    if not meanings or not any(m["meanings"] for m in meanings):
        print("No meaning")
        meanings=[{"pos":"web_translate","meanings":fall_back_google_translate(surface_form)}]
    
    romanji_reading=kana_to_romanji(reading)

    return {
        "meanings": meanings,
        "romanji_reading":  romanji_reading,
        "found":    True
    }
  
    
def kana_to_romanji(kana:str):
    """ 
    return romanji pronunciation reading
    
    """
    romaji_reading=converter.romaji(text=kana,capitalize=False)
    
    return romaji_reading



    
    
BASE_DIR = Path(__file__).resolve().parent.parent 
key_path=BASE_DIR / "gct_key.json"
client = translate.TranslationServiceClient.from_service_account_json(key_path)

parent = "projects/nlp-image-ocr/locations/global"

def fall_back_google_translate(japanese_form:str):
    print("Google Translation Running!")
    response = client.translate_text(
        contents=[japanese_form],
        target_language_code="en",
        parent=parent
        )
    # print(response.translations)

    return [t.translated_text for t in response.translations]


import re

def is_japanese(text):
    return re.search(r'[\u3040-\u30ff\u4e00-\u9fff]', text) is not None



# print(lookup_word_full("歌っ"))