from services.youtube_api_service import fetch_caption_tracks, fetch_video_metadata
from utils.video_validation_helpers import (
    check_video_japanese_suitability,
    extract_video_id,
)


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
