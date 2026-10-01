import base64
import io
import logging
from concurrent.futures import ThreadPoolExecutor, wait
from pathlib import Path

import fugashi
import librosa
import torch
from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from faster_whisper import WhisperModel
from sqlalchemy.orm import Session

from db.base import get_db
from schemas.user import UserRead
from services.auth.authentication_service import get_current_user
from services.external.gemini_api_service import get_pronunciation_feedback_from_gemini
from services.external.youtube_api_service import download_audio
from utils.shadowing_helpers import (
    analyze_pitch_accent,
    calculate_cer,
    convert_to_katakana,
    get_caption_error,
    transcribe_audio,
)
from utils.step_timer import StepTimer, timed

logger = logging.getLogger(__name__)

# Background threads for pitch analysis, so it overlaps with transcription.
_pitch_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="pitch")

router = APIRouter(prefix="/shadowing")


@router.post("/pronunciation_score")
def pronunciation_score(
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
    caption: str = Body(...),
    start_time: float = Body(0.0),
    end_time: float = Body(None),
    video_id: str = Body(None),
):
    print(
        f"File: {file.filename}\nFile Type: {file.content_type}\nCaption: {caption}\nStart Time: {start_time}\nEnd Time: {end_time}\nVideo ID: {video_id}"
    )
    timer = StepTimer()
    with timed(timer, "read_upload"):
        audio_bytes = file.file.read()
    upload_path = f"temp_audios/uploaded_{file.filename}"
    with timed(timer, "write_upload"):
        with open(upload_path, "wb") as f:
            f.write(audio_bytes)

    def run_pitch_analysis():
        # Download reference audio
        if video_id and Path(f"temp_audios/{video_id}.wav").exists() == False:
            print(f"Downloading audio for video ID: {video_id}")
            with timed(timer, "ref_download"):
                download_audio(video_id, "temp_audios", extract_wav=True)
        print(f"Analyzing pitch accent for video ID: {video_id}")
        return analyze_pitch_accent(
            f"temp_audios/{video_id}.wav",
            upload_path,
            start_time=start_time,
            end_time=end_time,
            timer=timer,
        )

    pitch_future = None
    try:
        # Pitch analysis (CPU) doesn't depend on the transcript, so run it
        # alongside Whisper (GPU) instead of after it.
        pitch_future = _pitch_executor.submit(run_pitch_analysis)

        # Transcribe the audio and convert to katakana
        user_katakana = transcribe_audio(io.BytesIO(audio_bytes), timer=timer)
        print(f"User katakana: {user_katakana}")
        # Compare with the caption (also converted to katakana)
        with timed(timer, "caption_compare"):
            caption_katakana = convert_to_katakana(caption)
            cer, wrong_indices = calculate_cer(caption_katakana, user_katakana)
            caption_error = get_caption_error(caption_katakana, wrong_indices)
        print(f"Caption katakana: {caption_katakana}")
        print(f"CER: {cer}")
        print(f"Caption error: {caption_error}")

        with timed(timer, "wait_pitch"):
            pitch_result = pitch_future.result()
        print(f"Pitch score: {pitch_result['score']}")
    finally:
        # If transcription failed, let the pitch thread finish with the file first.
        if pitch_future is not None:
            wait([pitch_future])
        # Delete temporary audio files
        Path(upload_path).unlink(missing_ok=True)

    logger.info(f"[score-timing] video={video_id} {timer.summary()}")

    return {
        "cer": cer,
        "user_katakana": user_katakana,
        "caption_katakana": caption_katakana,
        "pitch_score": pitch_result["score"],
        "user_pitch": pitch_result["aligned_target"].tolist(),
        "reference_pitch": pitch_result["aligned_ref"].tolist(),
        "caption_error": caption_error,
    }


@router.post("/explain")
def explain_pronunciation_score(
    cer: float = Body(...),
    pitch_score: float = Body(...),
    user_katakana: str = Body(...),
    caption_katakana: str = Body(...),
    user_pitch: list[float] = Body(...),
    reference_pitch: list[float] = Body(...),
    caption: str = Body(...),
    current_user: UserRead = Depends(get_current_user),
):
    try:
        explanation = get_pronunciation_feedback_from_gemini(
            cer=cer,
            pitch_score=pitch_score,
            user_katakana=user_katakana,
            caption_katakana=caption_katakana,
            user_pitch=user_pitch,
            reference_pitch=reference_pitch,
            caption=caption,
        )
        return explanation
    except Exception as e:
        raise HTTPException(status_code=500, detail="Service Unavailable")
