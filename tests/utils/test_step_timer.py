import pytest

from utils.step_timer import StepTimer, timed

pytestmark = [pytest.mark.unit]


def test_steps_are_summed_and_summarised():
    timer = StepTimer()
    with timer.step("pyin"):
        pass
    with timer.step("pyin"):
        pass
    timer.note("user_audio_s", 3.456)

    summary = timer.summary()

    assert list(timer.steps) == ["pyin"]
    assert summary.startswith("pyin=")
    assert "user_audio_s=3.46" in summary
    assert "total=" in summary


def test_timed_without_timer_is_a_no_op():
    with timed(None, "anything"):
        value = 1
    assert value == 1


def test_step_records_time_even_when_the_block_raises():
    timer = StepTimer()
    with pytest.raises(ValueError):
        with timer.step("boom"):
            raise ValueError
    assert "boom" in timer.steps
