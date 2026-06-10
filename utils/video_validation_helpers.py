import re

# Youtube has 4 distinct url patterns
YOUTUBE_URL_PATTERNS = [
    r"(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})",
    r"(?:https?://)?(?:www\.)?youtube\.com/shorts/([a-zA-Z0-9_-]{11})",
    r"(?:https?://)?youtu\.be/([a-zA-Z0-9_-]{11})",
    r"(?:https?://)?(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]{11})",
]


def extract_video_id(url: str) -> str | None:
    """Extract video id from youtube url of any form"""

    url = url.strip()
    for pattern in YOUTUBE_URL_PATTERNS:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def check_video_japanese_suitability(metadata: dict, caption_tracks: list[dict]):
    """Checks whether the video is Japanese Language video using heuristics"""

    default_lang = metadata.get("default_language") or ""
    audio_lang = metadata.get("default_audio_language") or ""
    is_japanese_language = default_lang.startswith("ja") or audio_lang.startswith("ja")

    japanese_captions = [
        track
        for track in caption_tracks
        if track.get("snippet", {}).get("language", "").startswith("ja")
    ]

    has_japanese_captions = len(japanese_captions) > 0

    if not has_japanese_captions:
        return {
            "is_suitable": False,
            "has_japanese_captions": False,
            "reason": "No Japanese Captions for this video.",
            "available_captions": japanese_captions,
        }

    if not is_japanese_language:
        return {
            "is_suitable": False,
            "has_japanese_captions": True,
            "reason": "Audio Language is not Japanese",
            "available_captions": japanese_captions,
        }

    return {
        "is_suitable": True,
        "has_japanese_captions": True,
        "reason": None,
        "available_captions": japanese_captions,
    }


# def compute_difficulty(video_vocab: list[dict]) -> str:
#     """
#     Returns a single difficulty label: beginner, intermediate, advanced, unknown.
#     """
#     tier_counts = {"N5": 0, "N4": 0, "N3": 0, "N2": 0, "N1": 0}
#     total = 0

#     for word in video_vocab:
#         tier = word.get("jlpt_tier", "UNKNOWN")
#         freq = word.get("frequency", 1)
#         if tier in tier_counts:
#             tier_counts[tier] += freq
#             total += freq

#     if total == 0:
#         return "unknown"

#     beginner_ratio = (tier_counts["N5"] + tier_counts["N4"]) / total
#     advanced_ratio = (tier_counts["N2"] + tier_counts["N1"]) / total

#     if beginner_ratio >= 0.6:
#         return "beginner"
#     elif advanced_ratio >= 0.4:
#         return "advanced"
#     else:
#         return "intermediate"
