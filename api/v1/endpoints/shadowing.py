from fastapi import APIRouter, Body, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
import torch
from db.base import get_db
from pathlib import Path
import librosa
import io
import fugashi
from faster_whisper import WhisperModel
import base64
from services.gemini_api_service import get_pronunciation_feedback_from_gemini
from utils.shadowing_helpers import transcribe_audio, analyze_pitch_accent, convert_to_katakana, calculate_cer, get_caption_error
from services.youtube_api_service import download_audio

router = APIRouter(prefix="/shadowing")

@router.post("/pronunciation_score")
def pronunciation_score(db: Session = Depends(get_db),
                        file: UploadFile = File(...),
                        caption: str = Body(...),
                        start_time: float = Body(0.0),
                        end_time: float = Body(None),
                        video_id: str = Body(None)):
    print(f"File: {file.filename}\nFile Type: {file.content_type}\nCaption: {caption}\nStart Time: {start_time}\nEnd Time: {end_time}\nVideo ID: {video_id}")
    audio = io.BytesIO(file.file.read())
    # Transcribe the audio and convert to katakana
    user_katakana = transcribe_audio(audio)
    print(f"User katakana: {user_katakana}")
    # Compare with the caption (also converted to katakana)
    caption_katakana = convert_to_katakana(caption)
    print(f"Caption katakana: {caption_katakana}")
    cer, wrong_indices = calculate_cer(caption_katakana, user_katakana)
    caption_error = get_caption_error(caption_katakana, wrong_indices)
    print(f"CER: {cer}")
    print(f"Caption error: {caption_error}")

    # Download reference audio
    if video_id and Path(f"temp_audios/{video_id}.wav").exists() == False:
        print(f"Downloading audio for video ID: {video_id}")
        download_audio(video_id, "temp_audios", extract_wav=True)

    with open(f'temp_audios/uploaded_{file.filename}', 'wb') as f:
        audio.seek(0)
        f.write(audio.read())
    # Analyze pitch accent
    print(f"Analyzing pitch accent for video ID: {video_id}")
    pitch_result = analyze_pitch_accent(f"temp_audios/{video_id}.wav", f"temp_audios/uploaded_{file.filename}", start_time=start_time, end_time=end_time)
    print(f"Pitch score: {pitch_result['score']}")
    # Delete temporary audio files
    Path(f"temp_audios/uploaded_{file.filename}").unlink(missing_ok=True)

    return {
        "cer": cer,
        "user_katakana": user_katakana,
        "caption_katakana": caption_katakana,
        "pitch_score": pitch_result["score"],
        "user_pitch": pitch_result["normalized_target"].tolist(),
        "reference_pitch": pitch_result["normalized_ref"].tolist(),
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
        raise HTTPException(status_code=404, detail="Not Found")