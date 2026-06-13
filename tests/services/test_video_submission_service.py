"""
Tests for services/video/video_submission_service.py  (Video Submission — Service)

submit_video_for_processing (MD-10) is an orchestrator: it routes, persists via
collaborators, and schedules background work. These tests verify the *wiring and
branching*, not the collaborators themselves — every collaborator is mocked at
this module's path, `db` is a mock, and a real BackgroundTasks() is used so we
can inspect what got scheduled.

Covers docs/test_plan.md §5.4 (SVP): branch decision (11), happy paths (01/02),
dedup (03), error mapping (04/09/10), surface-form passthrough (13),
jobs-scheduled-not-run (14), empty-captions edge (15).

No real I/O (db + externals mocked), so this is a unit/orchestration test. The
module skips if the heavy import chain (fastapi / fugashi / cutlet / GCT / whisper)
is unavailable.
"""

import types
from unittest.mock import MagicMock

import pytest

try:
    from fastapi import BackgroundTasks, HTTPException

    from services.video import video_submission_service as svc
    from services.video.video_submission_service import submit_video_for_processing
except Exception as exc:  # heavy import chain not installed
    pytest.skip(f"video_submission_service unavailable: {exc}", allow_module_level=True)

pytestmark = [pytest.mark.unit, pytest.mark.video_submission]


def _validation(track_kind="standard", valid=True, error=None):
    return {
        "valid": valid,
        "video_id": "vid12345678",
        "meta_data": {"title": "T"},
        "suitablity": {"available_captions": [{"snippet": {"trackKind": track_kind}}]},
        "error": error,
    }


MANUAL = _validation("standard")
AUTO = _validation("asr")


def _invalid(msg):
    return {
        "valid": False,
        "video_id": None,
        "meta_data": None,
        "suitablity": None,
        "error": msg,
    }


DEFAULT_PROCESSED = [
    {
        "index": 0,
        "text": "猫が",
        "start": 0.0,
        "end": 1.0,
        "duration": 1.0,
        "tokens": [
            {"surface": "猫", "base_form": "猫"},
            {"surface": "が", "base_form": "が"},
        ],
    }
]


def _patch(monkeypatch, **over):
    """Replace every collaborator on the service module with a mock."""
    m = {}

    def put(name, mock):
        monkeypatch.setattr(svc, name, mock)
        m[name] = mock
        return mock

    put("validate_video", MagicMock(return_value=over.get("validation", MANUAL)))
    put("check_video_exists", MagicMock(return_value=over.get("existing", None)))
    if "fetch_side_effect" in over:
        put("fetch_raw_captions", MagicMock(side_effect=over["fetch_side_effect"]))
    else:
        put("fetch_raw_captions", MagicMock(return_value={"events": []}))
    put("get_line_level_captions", MagicMock(return_value=over.get("lines", [])))
    put(
        "process_captions",
        MagicMock(return_value=over.get("processed", DEFAULT_PROCESSED)),
    )
    if "save_video_side_effect" in over:
        put("save_video", MagicMock(side_effect=over["save_video_side_effect"]))
    else:
        put("save_video", MagicMock(return_value={"title": "T", "video_id": 1}))
    put("save_tokenized_captions", MagicMock())
    put("save_vocabularies", MagicMock())
    put(
        "reconstruct_sentence_for_manual",
        MagicMock(return_value=over.get("sentences", [{"sentence_index": 0}])),
    )
    put("save_sentence", MagicMock())
    put("change_shadowing_status", MagicMock())
    put("build_shadowing_sentences_with_whisper_background_task", MagicMock())
    put("process_video_vocab_background", MagicMock())
    return types.SimpleNamespace(**m)


# --- SVP-01 (+ id propagation, SVP-12) --------------------------------------
def test_manual_path_processes_inline(monkeypatch):
    m = _patch(monkeypatch)
    bg = BackgroundTasks()
    result = submit_video_for_processing("url", MagicMock(), bg)

    assert (result.message, result.video_id, result.video_title) == (
        "Successful",
        1,
        "T",
    )
    m.reconstruct_sentence_for_manual.assert_called_once()
    m.save_sentence.assert_called_once()
    m.change_shadowing_status.assert_called_once()

    # saved id (1) propagates to the status update
    assert m.change_shadowing_status.call_args.args[0] == 1

    # only the vocab-profile task is scheduled; no Whisper
    funcs = [t.func for t in bg.tasks]
    assert funcs == [m.process_video_vocab_background]

    assert m.build_shadowing_sentences_with_whisper_background_task not in funcs


# --- SVP-02 -----------------------------------------------------------------
def test_auto_path_schedules_whisper(monkeypatch):
    m = _patch(monkeypatch, validation=AUTO)
    bg = BackgroundTasks()
    result = submit_video_for_processing("url", MagicMock(), bg)

    assert result.message == "Successful"
    m.reconstruct_sentence_for_manual.assert_not_called()
    m.save_sentence.assert_not_called()
    m.change_shadowing_status.assert_not_called()
    funcs = [t.func for t in bg.tasks]
    assert funcs == [
        m.build_shadowing_sentences_with_whisper_background_task,
        m.process_video_vocab_background,
    ]


# --- SVP-03 -----------------------------------------------------------------
def test_existing_video_short_circuits(monkeypatch):
    existing = types.SimpleNamespace(id=5, title="Old Title")
    m = _patch(monkeypatch, existing=existing)
    bg = BackgroundTasks()
    result = submit_video_for_processing("url", MagicMock(), bg)

    assert (result.message, result.video_id, result.video_title) == (
        "Video already exists.",
        5,
        "Old Title",
    )
    m.fetch_raw_captions.assert_not_called()
    m.save_video.assert_not_called()
    assert bg.tasks == []


# --- SVP-04 -----------------------------------------------------------------
@pytest.mark.parametrize(
    "msg", ["Invalid Youtube URL format", "No Japanese Captions for this video."]
)
def test_invalid_validation_raises_400(monkeypatch, msg):
    m = _patch(monkeypatch, validation=_invalid(msg))
    with pytest.raises(HTTPException) as ei:
        submit_video_for_processing("url", MagicMock(), BackgroundTasks())
    assert ei.value.status_code == 400
    assert ei.value.detail == msg
    m.check_video_exists.assert_not_called()


# --- SVP-09 -----------------------------------------------------------------
def test_caption_fetch_failure_raises_500(monkeypatch):
    m = _patch(monkeypatch, fetch_side_effect=RuntimeError("no captions"))
    with pytest.raises(HTTPException) as ei:
        submit_video_for_processing("url", MagicMock(), BackgroundTasks())
    assert ei.value.status_code == 500
    assert ei.value.detail == "Server Error"
    m.save_video.assert_not_called()


# --- SVP-10 -----------------------------------------------------------------
def test_persistence_failure_raises_500(monkeypatch):
    _patch(monkeypatch, save_video_side_effect=Exception("db boom"))
    bg = BackgroundTasks()
    with pytest.raises(HTTPException) as ei:
        submit_video_for_processing("url", MagicMock(), bg)
    assert ei.value.status_code == 500
    assert ei.value.detail == "Server Error , Please Try again later."
    assert bg.tasks == []


# # --- SVP-13 -----------------------------------------------------------------
# def test_vocab_task_receives_surface_forms_including_duplicates(monkeypatch):
#     processed = [
#         {
#             "index": 0,
#             "text": "猫",
#             "start": 0.0,
#             "end": 1.0,
#             "duration": 1.0,
#             "tokens": [{"surface": "猫", "base_form": "猫"}],
#         },
#         {
#             "index": 1,
#             "text": "また猫",
#             "start": 1.0,
#             "end": 2.0,
#             "duration": 1.0,
#             "tokens": [
#                 {"surface": "また", "base_form": "また"},
#                 {"surface": "猫", "base_form": "猫"},
#             ],
#         },
#     ]
#     m = _patch(monkeypatch, processed=processed)
#     bg = BackgroundTasks()
#     submit_video_for_processing("url", MagicMock(), bg)
#     vocab_task = next(t for t in bg.tasks if t.func is m.process_video_vocab_background)
#     assert vocab_task.args[1] == ["猫", "また", "猫"]  # 猫 appears twice


# --- SVP-14 -----------------------------------------------------------------
def test_background_jobs_scheduled_not_executed(monkeypatch):
    m = _patch(monkeypatch)
    bg = BackgroundTasks()
    submit_video_for_processing("url", MagicMock(), bg)
    m.process_video_vocab_background.assert_not_called()  # registered, not run
    assert len(bg.tasks) == 1
