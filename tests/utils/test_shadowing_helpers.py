import importlib
import sys
import types

import numpy as np
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.video_submission]


@pytest.fixture()
def shadowing_helpers(monkeypatch):
    class StubTagger:
        def __call__(self, text):
            return []

    fugashi = types.SimpleNamespace(Tagger=lambda: StubTagger())
    librosa = types.SimpleNamespace(
        load=lambda *args, **kwargs: (np.array([], dtype=float), kwargs.get("sr")),
        note_to_hz=lambda note: 65.0 if note == "C2" else 2093.0,
        pyin=lambda *args, **kwargs: (
            np.array([], dtype=float),
            np.array([], dtype=bool),
            np.array([], dtype=float),
        ),
    )
    whisper_service = types.SimpleNamespace(
        get_model=lambda name: object(),
        transcribe_words=lambda *args, **kwargs: [],
    )

    monkeypatch.setitem(sys.modules, "fugashi", fugashi)
    monkeypatch.setitem(sys.modules, "librosa", librosa)
    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace())
    monkeypatch.setitem(sys.modules, "whisper", types.SimpleNamespace())
    monkeypatch.setitem(
        sys.modules,
        "faster_whisper",
        types.SimpleNamespace(WhisperModel=object),
    )
    monkeypatch.setitem(
        sys.modules,
        "fastdtw",
        types.SimpleNamespace(fastdtw=lambda *args, **kwargs: (0.0, [(0, 0)])),
    )
    monkeypatch.setitem(
        sys.modules,
        "yt_dlp",
        types.SimpleNamespace(YoutubeDL=object),
    )
    monkeypatch.setitem(
        sys.modules,
        "matplotlib",
        types.SimpleNamespace(pyplot=types.SimpleNamespace()),
    )
    monkeypatch.setitem(
        sys.modules,
        "matplotlib.pyplot",
        types.SimpleNamespace(),
    )
    monkeypatch.setitem(
        sys.modules,
        "services.external.whisper_service",
        whisper_service,
    )
    sys.modules.pop("utils.shadowing_helpers", None)
    module = importlib.import_module("utils.shadowing_helpers")
    yield module
    sys.modules.pop("utils.shadowing_helpers", None)


def test_calculate_cer_returns_zero_for_exact_match(shadowing_helpers):
    reference = [("今日", "キョウ"), ("は", "ワ")]
    target = [("今日", "キョウ"), ("は", "ワ")]

    cer, wrong_indices = shadowing_helpers.calculate_cer(reference, target)

    assert cer == 0
    assert wrong_indices == []


def test_calculate_cer_reports_substitution_index(shadowing_helpers):
    reference = [("今日", "キョウ"), ("は", "ワ")]
    target = [("今日", "キョウ"), ("が", "ガ")]

    cer, wrong_indices = shadowing_helpers.calculate_cer(reference, target)

    assert cer == pytest.approx(0.25)
    assert wrong_indices == [3]


def test_get_caption_error_marks_words_with_wrong_indices(shadowing_helpers):
    reference = [("今日", "キョウ"), ("は", "ワ"), ("いい", "イイ")]

    result = shadowing_helpers.get_caption_error(reference, wrong_indices=[3, 5])

    assert result == [("今日", True), ("は", False), ("いい", False)]


def test_normalize_pitch_centers_voiced_frames(shadowing_helpers):
    f0 = np.array([100.0, 200.0, 150.0])

    result = shadowing_helpers.normalize_pitch(f0)

    expected = np.array(
        [
            12 * np.log2(100.0 / 150.0),
            12 * np.log2(200.0 / 150.0),
            12 * np.log2(150.0 / 150.0),
        ]
    )
    np.testing.assert_allclose(result, expected)


def test_normalize_pitch_returns_input_when_no_voiced_frames(shadowing_helpers):
    f0 = np.array([0.0, 0.0])

    result = shadowing_helpers.normalize_pitch(f0)

    np.testing.assert_array_equal(result, f0)


# def test_compare_pitch_runs_dtw_and_returns_aligned_contours(
#     monkeypatch, shadowing_helpers
# ):
#     calls = {}

#     def fake_fastdtw(ref, target, radius, dist):
#         calls["ref"] = ref.copy()
#         calls["target"] = target.copy()
#         calls["dist"] = dist
#         calls["radius"] = radius
#         return 6.0, [(0, 0), (1, 1), (2, 1)]

#     monkeypatch.setattr(shadowing_helpers, "fastdtw", fake_fastdtw)

#     result = shadowing_helpers.compare_pitch(
#         np.array([0.0, 1.0, 2.0]),
#         np.array([3.0, 0.0]),
#     )

#     # Contours are reshaped to (n, 1) and passed to DTW without unvoiced filtering.
#     np.testing.assert_array_equal(calls["ref"], np.array([[0.0], [1.0], [2.0]]))
#     np.testing.assert_array_equal(calls["target"], np.array([[3.0], [0.0]]))
#     assert calls["dist"] is shadowing_helpers.euclidean


#     assert result["distance"] == 6.0
#     assert result["normalized_distance"] == 2.0  # 6.0 / len(path)
#     assert result["path"] == [(0, 0), (1, 1), (2, 1)]
#     assert result["path_length"] == 3
#     # aligned contours follow the DTW path, indexing the original arrays
#     np.testing.assert_array_equal(result["aligned_ref"], np.array([0.0, 1.0, 2.0]))
#     np.testing.assert_array_equal(result["aligned_target"], np.array([3.0, 0.0, 0.0]))
#     assert set(result) == {
#         "distance",
#         "normalized_distance",
#         "path",
#         "path_length",
#         "aligned_ref",
#         "aligned_target",
#     }
def test_compare_pitch_runs_dtw_and_returns_aligned_contours(
    monkeypatch, shadowing_helpers
):
    calls = {}

    def fake_fastdtw(ref, target, radius, dist):
        calls["ref"] = ref.copy()
        calls["target"] = target.copy()
        calls["dist"] = dist
        calls["radius"] = radius
        return 6.0, [(0, 0), (1, 0)]

    monkeypatch.setattr(shadowing_helpers, "fastdtw", fake_fastdtw)

    result = shadowing_helpers.compare_pitch(
        np.array([0.0, 1.0, 2.0]),
        np.array([3.0, 0.0]),
    )

    # Unvoiced (== 0) frames are dropped, and each contour gains a delta column:
    #   ref    [0,1,2] -> voiced [1,2] -> stacked [[1,1],[2,1]]
    #   target [3,0]   -> voiced [3]   -> stacked [[3,0]]
    np.testing.assert_array_equal(calls["ref"], np.array([[1.0, 1.0], [2.0, 1.0]]))
    np.testing.assert_array_equal(calls["target"], np.array([[3.0, 0.0]]))
    assert calls["dist"] is shadowing_helpers.euclidean
    assert calls["radius"] == 1

    assert result["distance"] == 6.0
    assert result["normalized_distance"] == 3.0  # 6.0 / len(path)
    assert result["path"] == [(0, 0), (1, 0)]
    assert result["path_length"] == 2

    # aligned contours follow the DTW path, reading column 0 of the stacked arrays
    np.testing.assert_array_equal(result["aligned_ref"], np.array([1.0, 2.0]))
    np.testing.assert_array_equal(result["aligned_target"], np.array([3.0, 3.0]))

    assert set(result) == {
        "distance",
        "normalized_distance",
        "path",
        "path_length",
        "aligned_ref",
        "aligned_target",
    }


@pytest.mark.parametrize(
    ("distance", "grade", "score"),
    [
        (0.25, "Excellent", 95.0),
        (1.0, "Good", 80.0),
        (2.0, "Fair", 60.0),
        (4.0, "Poor", 20.0),
        (6.0, "Poor", 0),
    ],
)
def test_score_accent_thresholds(shadowing_helpers, distance, grade, score):
    result = shadowing_helpers.score_accent(distance)

    assert result["grade"] == grade
    assert result["score"] == score
    assert result["feedback"]


def test_analyze_pitch_accent_composes_pitch_pipeline(monkeypatch, shadowing_helpers):
    calls = []
    ref_pitch = np.array([100.0, 200.0])
    target_pitch = np.array([150.0, 300.0])
    normalized_ref = np.array([-1.0, 1.0])
    normalized_target = np.array([-2.0, 2.0])
    aligned_ref_dtw = np.array([-1.0, 1.0, 1.0])
    aligned_target_dtw = np.array([-2.0, 2.0, 2.0])
    comparison = {
        "normalized_distance": 1.25,
        "aligned_ref": aligned_ref_dtw,
        "aligned_target": aligned_target_dtw,
    }
    score = {"grade": "Good", "score": 75.0}

    def fake_extract_pitch(audio_path, sr, start_time, end_time):
        calls.append((audio_path, sr, start_time, end_time))
        if audio_path == "reference.wav":
            return ref_pitch, sr
        return target_pitch, sr

    def fake_normalize_pitch(f0):
        if f0 is ref_pitch:
            return normalized_ref
        return normalized_target

    monkeypatch.setattr(shadowing_helpers, "extract_pitch", fake_extract_pitch)
    monkeypatch.setattr(shadowing_helpers, "normalize_pitch", fake_normalize_pitch)
    monkeypatch.setattr(
        shadowing_helpers, "compare_pitch", lambda ref, target: comparison
    )
    monkeypatch.setattr(
        shadowing_helpers, "score_accent", lambda normalized_distance: score
    )

    result = shadowing_helpers.analyze_pitch_accent(
        "reference.wav",
        "target.wav",
        sr=16000,
        start_time=1.5,
        end_time=3.0,
    )

    assert calls == [
        ("reference.wav", 16000, 1.5, 3.0),
        ("target.wav", 16000, 0.0, None),
    ]
    assert result == {
        "comparison": comparison,
        "score": score,
        "normalized_ref": normalized_ref,
        "normalized_target": normalized_target,
        "aligned_ref": aligned_ref_dtw,
        "aligned_target": aligned_target_dtw,
    }


def test_transcribe_audio_uses_medium_model_and_converts_text(
    monkeypatch, shadowing_helpers
):
    calls = {}

    class Segment:
        def __init__(self, text):
            self.text = text

    def fake_get_model(name):
        calls["model_name"] = name
        return "model"

    def fake_transcribe_words(file, model, **kwargs):
        calls["transcribe"] = (file, model, kwargs)
        return [Segment("こん"), Segment("にちは")]

    def fake_convert_to_katakana(text):
        calls["converted_text"] = text
        return [("こんにちは", "コンニチハ")]

    monkeypatch.setattr(shadowing_helpers, "get_model", fake_get_model)
    monkeypatch.setattr(shadowing_helpers, "transcribe_words", fake_transcribe_words)
    monkeypatch.setattr(
        shadowing_helpers, "convert_to_katakana", fake_convert_to_katakana
    )

    result = shadowing_helpers.transcribe_audio("audio-file")

    assert result == [("こんにちは", "コンニチハ")]
    assert calls["model_name"] == "medium"
    assert calls["transcribe"] == (
        "audio-file",
        "model",
        {"language": "ja", "vad_filter": True, "word_timestamps": False},
    )
    assert calls["converted_text"] == "こんにちは"
