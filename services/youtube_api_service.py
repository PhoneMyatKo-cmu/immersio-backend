import os

import httpx
from dotenv import load_dotenv

load_dotenv()

YOUTUBE_API_BASE_URL = os.getenv("YOUTUBE_API_BASE_URL")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")


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
