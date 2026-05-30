from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session
import torch
from db.base import get_db

import librosa
import whisper
import fugashi
from faster_whisper import WhisperModel
from utils.shadowing_helpers import download_youtube_audio, transcribe_audio, analyze_pitch_accent, convert_to_katakana, calculate_cer

router = APIRouter(prefix="/shadowing")

@router.post("/pronunciation_score")
def pronunciation_score(db: Session = Depends(get_db),
                        file: UploadFile = File(...),
                        caption: str = None,
                        start_time: float = 0.0,
                        end_time: float = None,
                        video_id: str = None):
    # Transcribe the audio and convert to katakana
    user_katakana = transcribe_audio(file.file)
    # Compare with the caption (also converted to katakana)
    caption_katakana = convert_to_katakana(caption)
    cer = calculate_cer(caption_katakana, user_katakana)

    # Download reference audio
    if video_id and File.exists(f"{video_id}_audio.wav") == False:
        download_youtube_audio(f"https://www.youtube.com/watch?v={video_id}", f"temp_audios/{video_id}_audio.wav")

    # Analyze pitch accent
    pitch_result = analyze_pitch_accent(file.file, f"temp_audios/{video_id}_audio.wav", start_time=start_time, end_time=end_time)

    return {
        "cer": cer,
        "pitch_score": pitch_result["score"],
        "pitch_comparison_figure": pitch_result["figure"]
    }


@router.post("/test")
def test_endpoint(db: Session = Depends(get_db), file: UploadFile = File(...)):

    # Load the Whisper model
    model = WhisperModel("medium", device='cuda' if torch.cuda.is_available() else 'cpu', compute_type="float16" if torch.cuda.is_available() else "int8")

    # Transcribe the audio
    result = model.transcribe(file.file, language='ja')

    # Convert the transcription to katakana using fugashi
    tagger = fugashi.Tagger()
    

    return {"transcription": result}