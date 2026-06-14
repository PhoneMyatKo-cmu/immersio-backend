import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.v1.endpoints import shadowing as shadowing_endpoint
from db.base import get_db
from services.auth.authentication_service import get_current_user

pytestmark = [pytest.mark.integration, pytest.mark.video_submission]


class _Pitch(list):
    def tolist(self):
        return list(self)


@pytest.fixture()
def shadowing_client():
    app = FastAPI()
    db = object()

    def override_get_db():
        yield db

    class StubUser:
        id = 1
        email = "test@example.com"

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: StubUser()
    app.include_router(shadowing_endpoint.router)

    with TestClient(app) as client:
        yield client


def test_pronunciation_score_returns_metrics_and_pitch_data(
    monkeypatch, tmp_path, shadowing_client
):
    temp_audios = tmp_path / "temp_audios"
    temp_audios.mkdir()
    monkeypatch.chdir(tmp_path)
    calls = {}

    def fake_transcribe_audio(audio):
        calls["audio_bytes"] = audio.read()
        audio.seek(0)
        return "コンニチハ"

    def fake_download_audio(video_id, output_dir, extract_wav):
        calls["download_audio"] = {
            "video_id": video_id,
            "output_dir": output_dir,
            "extract_wav": extract_wav,
        }

    def fake_analyze_pitch_accent(ref_audio_path, target_audio_path, **kwargs):
        calls["analyze_pitch_accent"] = {
            "ref_audio_path": ref_audio_path,
            "target_audio_path": target_audio_path,
            **kwargs,
        }
        return {
            "score": 92.5,
            "normalized_target": _Pitch([0.1, 0.2, 0.3]),
            "normalized_ref": _Pitch([0.3, 0.2, 0.1]),
        }

    monkeypatch.setattr(shadowing_endpoint, "transcribe_audio", fake_transcribe_audio)
    monkeypatch.setattr(
        shadowing_endpoint, "convert_to_katakana", lambda caption: "コンニチハ"
    )
    monkeypatch.setattr(
        shadowing_endpoint, "calculate_cer", lambda expected, actual: (0.25, [1])
    )
    monkeypatch.setattr(
        shadowing_endpoint, "get_caption_error", lambda caption, wrong: ["ン"]
    )
    monkeypatch.setattr(shadowing_endpoint, "download_audio", fake_download_audio)
    monkeypatch.setattr(
        shadowing_endpoint, "analyze_pitch_accent", fake_analyze_pitch_accent
    )

    response = shadowing_client.post(
        "/shadowing/pronunciation_score",
        data={
            "caption": "こんにちは",
            "start_time": "1.5",
            "end_time": "3.0",
            "video_id": "yt123",
        },
        files={"file": ("sample.wav", b"fake-audio", "audio/wav")},
    )

    assert response.status_code == 200
    assert response.json() == {
        "cer": 0.25,
        "user_katakana": "コンニチハ",
        "caption_katakana": "コンニチハ",
        "pitch_score": 92.5,
        "user_pitch": [0.1, 0.2, 0.3],
        "reference_pitch": [0.3, 0.2, 0.1],
        "caption_error": ["ン"],
    }
    assert calls["audio_bytes"] == b"fake-audio"
    assert calls["download_audio"] == {
        "video_id": "yt123",
        "output_dir": "temp_audios",
        "extract_wav": True,
    }
    assert calls["analyze_pitch_accent"] == {
        "ref_audio_path": "temp_audios/yt123.wav",
        "target_audio_path": "temp_audios/uploaded_sample.wav",
        "start_time": 1.5,
        "end_time": 3.0,
    }
    assert not (temp_audios / "uploaded_sample.wav").exists()


def test_pronunciation_score_requires_uploaded_file(shadowing_client):
    response = shadowing_client.post(
        "/shadowing/pronunciation_score",
        data={"caption": "こんにちは"},
    )

    assert response.status_code == 422


def test_explain_pronunciation_score_returns_feedback(monkeypatch, shadowing_client):
    calls = {}
    feedback = {
        "overall_feedback": "Nice work.",
        "pronunciation_feedback": ["Your sounds are clear."],
        "pitch_feedback": ["Pitch is close."],
        "practice_suggestions": ["Repeat the sentence slowly."],
    }

    def fake_get_feedback(**kwargs):
        calls["feedback_kwargs"] = kwargs
        return feedback

    monkeypatch.setattr(
        shadowing_endpoint,
        "get_pronunciation_feedback_from_gemini",
        fake_get_feedback,
    )

    payload = {
        "cer": 0.1,
        "pitch_score": 88.0,
        "user_katakana": "コンニチハ",
        "caption_katakana": "コンニチハ",
        "user_pitch": [0.1, 0.2],
        "reference_pitch": [0.2, 0.1],
        "caption": "こんにちは",
    }

    response = shadowing_client.post("/shadowing/explain", json=payload)

    assert response.status_code == 200
    assert response.json() == feedback
    assert calls["feedback_kwargs"] == payload


def test_explain_pronunciation_score_returns_500_when_feedback_fails(
    monkeypatch, shadowing_client
):
    def fake_get_feedback(**kwargs):
        raise RuntimeError("Gemini unavailable")

    monkeypatch.setattr(
        shadowing_endpoint,
        "get_pronunciation_feedback_from_gemini",
        fake_get_feedback,
    )

    response = shadowing_client.post(
        "/shadowing/explain",
        json={
            "cer": 0.1,
            "pitch_score": 88.0,
            "user_katakana": "コンニチハ",
            "caption_katakana": "コンニチハ",
            "user_pitch": [0.1, 0.2],
            "reference_pitch": [0.2, 0.1],
            "caption": "こんにちは",
        },
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "Service Unavailable"}
