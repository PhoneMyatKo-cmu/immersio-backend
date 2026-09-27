import json
import os
import tempfile

import httpx
import yt_dlp
from dotenv import load_dotenv
from yt_dlp import YoutubeDL

load_dotenv()

YOUTUBE_API_BASE_URL = os.getenv("YOUTUBE_API_BASE_URL")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
# YouTube blocks datacenter IPs (e.g. EC2) for yt-dlp scraping. Either sign
# the requests in with an exported cookies.txt (YOUTUBE_COOKIES = file path)
# and/or route them through a residential proxy (YOUTUBE_PROXY). The Data API
# calls don't need either.
YOUTUBE_PROXY = os.getenv("YOUTUBE_PROXY") or None
YOUTUBE_COOKIES = os.getenv("YOUTUBE_COOKIES") or None
# YouTube 429s caption downloads that lack a PO token. With a PO token provider
# running (bgutil-ytdlp-pot-provider, see deploy/README.md), set this to 1 so
# yt-dlp always attaches one. Leave unset where no provider runs (local dev).
YOUTUBE_FETCH_POT = os.getenv("YOUTUBE_FETCH_POT") == "1"


def _yt_dlp_network_opts() -> dict:
    opts = {}
    if YOUTUBE_PROXY:
        opts["proxy"] = YOUTUBE_PROXY
    if YOUTUBE_COOKIES:
        opts["cookiefile"] = YOUTUBE_COOKIES
    return opts


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


def _pick_caption_track(info: dict, lang: str) -> tuple[str | None, bool]:
    """Return (track key, is_auto) for the best caption track in `lang`.

    Prefers human subtitles, then the original-language auto captions
    ("<lang>-orig"). The bare auto "<lang>" track is a machine translation
    (tlang=<lang>) that YouTube rate-limits hard (HTTP 429), so it is only a
    last resort.
    """
    manual = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}
    if lang in manual:
        return lang, False
    if f"{lang}-orig" in auto:
        return f"{lang}-orig", True
    if lang in auto:
        return lang, True
    return None, False


def fetch_raw_captions(video_id: str, lang: str = "ja") -> dict:
    """Sub-segments level caption fetching.

    Picks the caption track from the video's metadata first, then lets
    yt-dlp's own subtitle downloader write that one json3 file (the same path
    as `yt-dlp --write-subs`).
    """

    url = f"https://www.youtube.com/watch?v={video_id}"
    with tempfile.TemporaryDirectory() as tmp_dir:
        ydl_opts = {
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "subtitlesformat": "json3",
            "outtmpl": os.path.join(tmp_dir, "%(id)s.%(ext)s"),
            **_yt_dlp_network_opts(),
        }
        if YOUTUBE_FETCH_POT:
            ydl_opts["extractor_args"] = {"youtube": {"fetch_pot": ["always"]}}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # process=False: read the available tracks without downloading.
            info = ydl.extract_info(url, download=False, process=False)
            track, is_auto = _pick_caption_track(info, lang)
            if track is None:
                raise RuntimeError(f"No {lang} captions available for {video_id}")

            ydl.params.update(
                {
                    "writesubtitles": not is_auto,
                    "writeautomaticsub": is_auto,
                    "subtitleslangs": [track],
                }
            )
            ydl.process_ie_result(info, download=True)

        caption_path = os.path.join(tmp_dir, f"{video_id}.{track}.json3")
        if not os.path.exists(caption_path):
            raise RuntimeError(f"No {lang} json3 captions available for {video_id}")
        with open(caption_path, encoding="utf-8") as f:
            return json.load(f)

def download_audio(url_or_id: str, out_dir: str, extract_wav: bool = False) -> str:
    """
    Download the best audio stream to out_dir and return its path.

    Args:
        url_or_id:    Full YouTube URL or bare video ID.
        out_dir:      Directory to save the file.
        extract_wav:  If True, transcode to WAV via FFmpeg (requires ffmpeg on PATH).
                      Defaults to False — faster-whisper can decode m4a/webm directly.

    Returns:
        Absolute path to the downloaded (or transcoded) file.
    """
    url = (
        url_or_id
        if url_or_id.startswith("http")
        else f"https://www.youtube.com/watch?v={url_or_id}"
    )

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(out_dir, "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        # No player_client override: yt-dlp's defaults track YouTube changes,
        # and the android/ios clients can't use cookies.
        **_yt_dlp_network_opts(),
    }

    if extract_wav:
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "wav",
            "preferredquality": "192",
        }]

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    reqs = info.get("requested_downloads")
    if reqs and reqs[0].get("filepath"):
        return reqs[0]["filepath"]
    return ydl.prepare_filename(info)