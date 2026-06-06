"""
End-to-end pipeline:
    YouTube audio (yt-dlp) -> faster-whisper word-level transcript
    -> sentence reconstruction.

Feeds the WhisperModel.transcribe(..., word_timestamps=True) output directly
into reconstruct_sentences_from_whisper, so the segments are never re-shaped
in between — the reconstruction adapter consumes faster-whisper words as-is.

NOTE: this is CPU/GPU-heavy and blocking. Run it inside a background worker
(Celery / arq / RQ / FastAPI BackgroundTasks), not in the request that the
user is waiting on.
"""

import os
import tempfile
from typing import List, Optional

from faster_whisper import WhisperModel

# Adjust this import to wherever you placed the reconstruction module.
from yt_dlp import YoutubeDL

from utils.whisper_sentence_reconstruct import reconstruct_sentences_from_whisper

# =====================================================================
# Model singleton — load ONCE, reuse across calls.
# Re-instantiating WhisperModel per request reloads weights every time.
# =====================================================================

_MODEL: Optional[WhisperModel] = None
_MODEL_SIZE: Optional[str] = None


def _detect_device():
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


def get_model(model_size: str = "medium") -> WhisperModel:
    global _MODEL, _MODEL_SIZE
    if _MODEL is None or _MODEL_SIZE != model_size:
        device, compute_type = _detect_device()
        _MODEL = WhisperModel(model_size, device=device, compute_type=compute_type)
        _MODEL_SIZE = model_size
    return _MODEL


# =====================================================================
# Step 1: Download audio
# =====================================================================


def download_audio(url_or_id: str, out_dir: str) -> str:
    """
    Download the best audio-only stream to out_dir and return its path.

    No ffmpeg transcode here — faster-whisper decodes the container itself
    (via PyAV), so we hand it the raw m4a/webm directly. If you hit decode
    issues on exotic formats, add an FFmpegExtractAudio postprocessor to
    convert to wav (requires the ffmpeg binary on PATH).
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
        "extractor_args": {
            "youtube": {"player_client": ["web", "android", "ios"]},
        },
    }

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    # Most reliable post-download path lookup, with a fallback.
    reqs = info.get("requested_downloads")
    if reqs and reqs[0].get("filepath"):
        return reqs[0]["filepath"]
    return ydl.prepare_filename(info)


# =====================================================================
# Step 2: Transcribe with word-level timestamps
# =====================================================================


def transcribe_words(
    audio_path: str, model: WhisperModel, language: str = "ja", vad_filter: bool = True
) -> list:
    """
    Transcribe to faster-whisper segments WITH word-level timestamps and
    materialize the generator into a list (the reconstruction algo needs to
    iterate it, and listing it forces the full transcription to run).

    word_timestamps=True is REQUIRED — it's the whole reason the timing is
    audio-grounded. vad_filter skips silence (faster + cleaner), and the
    returned timestamps stay mapped to the original timeline so real pauses
    still show up as gaps for the segmenter. If gap-based breaks behave oddly,
    try vad_filter=False.
    """
    segments, _info = model.transcribe(
        audio_path,
        language=language,
        word_timestamps=True,
        vad_filter=vad_filter,
        beam_size=5,
    )
    return list(segments)


# =====================================================================
# Driver
# =====================================================================


def youtube_to_sentences(
    url_or_id: str,
    *,
    shadow: bool = True,
    model_size: str = "medium",
    language: str = "ja",
    vad_filter: bool = True,
) -> List[dict]:
    """
    Full pipeline. Returns the app-format sentence dicts
    ({text, start, end, duration, sentence_index}).

    Call from a background worker, then persist the result (and the precomputed
    furigana tokens) so the read path stays instant.
    """
    model = get_model(model_size)

    # Temp dir auto-deletes the audio once we leave the block. We materialize
    # the transcript (list) inside the block, so by the time the audio is
    # removed, transcription is finished and only the segments (in memory) are
    # needed for reconstruction.
    with tempfile.TemporaryDirectory() as tmp:
        audio_path = download_audio(url_or_id, tmp)
        segments = transcribe_words(
            audio_path, model, language=language, vad_filter=vad_filter
        )

    return reconstruct_sentences_from_whisper(segments, shadow=shadow)


if __name__ == "__main__":
    import json
    import sys

    vid = sys.argv[1] if len(sys.argv) > 1 else "dQw4w9WgXcQ"
    sentences = youtube_to_sentences(vid, shadow=True)
    print(json.dumps(sentences, ensure_ascii=False, indent=2))
