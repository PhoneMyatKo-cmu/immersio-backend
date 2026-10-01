import time
from contextlib import contextmanager, nullcontext


class StepTimer:
    """Collects wall-clock time per named step for one request.

    Repeated steps with the same name are summed. `note` records extra values
    (e.g. clip lengths) that are printed alongside the timings.
    """

    def __init__(self):
        self.steps: dict[str, float] = {}
        self.notes: dict[str, float] = {}
        self._start = time.perf_counter()

    @contextmanager
    def step(self, name: str):
        start = time.perf_counter()
        try:
            yield
        finally:
            self.steps[name] = self.steps.get(name, 0.0) + time.perf_counter() - start

    def note(self, name: str, value: float):
        self.notes[name] = value

    def summary(self) -> str:
        parts = [f"{name}={secs:.3f}s" for name, secs in self.steps.items()]
        parts += [f"{name}={value:.2f}" for name, value in self.notes.items()]
        parts.append(f"total={time.perf_counter() - self._start:.3f}s")
        return " ".join(parts)


def timed(timer: "StepTimer | None", name: str):
    """`timer.step(name)` when a timer is given, otherwise a no-op context."""
    return timer.step(name) if timer is not None else nullcontext()
