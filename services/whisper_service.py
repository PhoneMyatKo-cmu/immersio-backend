from typing import Optional

from faster_whisper import WhisperModel


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

def transcribe_words(
    audio_path: str, model: WhisperModel, language: str = "ja", vad_filter: bool = True, word_timestamps: bool = True
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
        word_timestamps=word_timestamps,
        vad_filter=vad_filter,
        beam_size=5,
    )
    return list(segments)