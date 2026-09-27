"""
Tests for services/external/whisper_service.py device selection.

[unit] faster_whisper and ctranslate2 are stubbed; no model is loaded.
"""

import importlib
import sys
import types

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.video_submission]


@pytest.fixture()
def whisper_service(monkeypatch):
    monkeypatch.setitem(
        sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=object)
    )
    sys.modules.pop("services.external.whisper_service", None)
    module = importlib.import_module("services.external.whisper_service")
    yield module
    sys.modules.pop("services.external.whisper_service", None)


@pytest.mark.parametrize(
    ("gpu_count", "expected"),
    [(1, ("cuda", "float16")), (0, ("cpu", "int8"))],
)
def test_detect_device_uses_ctranslate2_gpu_count(
    monkeypatch, whisper_service, gpu_count, expected
):
    monkeypatch.setitem(
        sys.modules,
        "ctranslate2",
        types.SimpleNamespace(get_cuda_device_count=lambda: gpu_count),
    )

    assert whisper_service._detect_device() == expected


def test_detect_device_falls_back_to_cpu_when_ctranslate2_errors(
    monkeypatch, whisper_service
):
    def broken():
        raise RuntimeError("CUDA driver version is insufficient")

    monkeypatch.setitem(
        sys.modules,
        "ctranslate2",
        types.SimpleNamespace(get_cuda_device_count=broken),
    )

    assert whisper_service._detect_device() == ("cpu", "int8")
