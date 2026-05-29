import os
import re

import httpx
from dotenv import load_dotenv

load_dotenv()


# Youtube has 4 distinct url patterns
YOUTUBE_URL_PATTERNS = [
    r"(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})",
    r"(?:https?://)?(?:www\.)?youtube\.com/shorts/([a-zA-Z0-9_-]{11})",
    r"(?:https?://)?youtu\.be/([a-zA-Z0-9_-]{11})",
    r"(?:https?://)?(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]{11})",
]

# To be put in environment variables file
YOUTUBE_API_BASE_URL = os.getenv("YOUTUBE_API_BASE_URL")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")


def extract_video_id(url: str) -> str | None:
    """Extract video id from youtube url of any form"""

    url = url.strip()
    for pattern in YOUTUBE_URL_PATTERNS:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def fetch_video_metadata(video_id: str) -> dict | None:
    """Check whether video id actually exists. If exists , extract
    meta data , else return none."""

    client = httpx.Client()
    response = client.get(
        f"{YOUTUBE_API_BASE_URL}/videos",
        params={
            "id": video_id,
            "part": "snippet,contentDetails,status",
            "key": YOUTUBE_API_KEY,
        },
    )

    if response.status_code != 200:
        raise Exception(f"Youtube Data API error:{response.status_code}")

    data = response.json()

    if not data.get("items"):
        return None

    item = data["items"][0]
    privacy_status = item.get("status", {})

    if privacy_status.get("privacyStatus") == "private":
        return None

    snippet = item["snippet"]
    content_details = item["contentDetails"]

    return {
        "video_id": video_id,
        "title": snippet.get("title"),
        "channel_name": snippet.get("channelTitle"),
        "thumbnail_url": snippet.get("thumbnails", {}).get("high", {}).get("url"),
        "duration_iso": content_details.get("duration"),
        "default_language": snippet.get("defaultLanguage"),
        "default_audio_language": snippet.get("defaultAudioLanguage"),
        "tags": snippet.get("tags", []),
        "duration": content_details.get("duration"),
    }


def fetch_caption_tracks(video_id: str) -> list[dict]:
    """
    Fetches available caption tracks for a video.
    Returns list of caption track objects.
    """

    client = httpx.Client()
    response = client.get(
        f"{YOUTUBE_API_BASE_URL}/captions",
        params={
            "videoId": video_id,
            "part": "snippet",
            "key": YOUTUBE_API_KEY,
        },
    )

    if response.status_code != 200:
        return []

    data = response.json()
    return data.get("items", [])


def check_video_japanese_suitability(metadata: dict, caption_tracks: list[dict]):
    """Checks whether the video is Japanese Language video using heuristics"""

    default_lang = metadata.get("default_language", "")
    audio_lang = metadata.get("default_audio_language", "")
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


def validate_video(url: str):
    """Validation pipeline to check whether the url is valid Japanese Youtube video useful for learning."""

    video_id = extract_video_id(url)
    if not video_id:
        return {
            "valid": False,
            "video_id": None,
            "meta_data": None,
            "suitablity": None,
            "error": "Invalid Youtube URL format",
        }

    try:
        meta_data = fetch_video_metadata(video_id)
    except Exception:
        return {
            "valid": False,
            "video_id": video_id,
            "meta_data": None,
            "suitablity": None,
            "error": "Error on Youtube API",
        }

    if not meta_data:
        return {
            "valid": False,
            "video_id": video_id,
            "meta_data": None,
            "suitablity": None,
            "error": "Video Unavailable.",
        }

    caption_tracks = fetch_caption_tracks(video_id)
    japanese_suitablility = check_video_japanese_suitability(meta_data, caption_tracks)

    if not japanese_suitablility["is_suitable"]:
        return {
            "valid": False,
            "video_id": video_id,
            "meta_data": meta_data,
            "suitablity": japanese_suitablility,
            "error": japanese_suitablility["reason"],
        }

    return {
        "valid": True,
        "video_id": video_id,
        "meta_data": meta_data,
        "suitablity": japanese_suitablility,
        "error": None,
    }


def compute_difficulty(video_vocab: list[dict]) -> str:
    """
    Returns a single difficulty label: beginner, intermediate, advanced, unknown.
    """
    tier_counts = {"N5": 0, "N4": 0, "N3": 0, "N2": 0, "N1": 0}
    total = 0

    for word in video_vocab:
        tier = word.get("jlpt_tier", "UNKNOWN")
        freq = word.get("frequency", 1)
        if tier in tier_counts:
            tier_counts[tier] += freq
            total += freq

    if total == 0:
        return "unknown"

    beginner_ratio = (tier_counts["N5"] + tier_counts["N4"]) / total
    advanced_ratio = (tier_counts["N2"] + tier_counts["N1"]) / total

    if beginner_ratio >= 0.6:
        return "beginner"
    elif advanced_ratio >= 0.4:
        return "advanced"
    else:
        return "intermediate"
