from __future__ import annotations

from datetime import timedelta
from types import TracebackType

from django.utils.timezone import now as tz_now


class stopwatch:
    def __enter__(self) -> stopwatch:
        self.started_at = tz_now()
        self.stopped_at = None
        self.in_progress = True
        return self

    def __exit__(
        self,
        exc_type: type[Exception],
        exc_value: Exception,
        traceback: TracebackType,
    ) -> None:
        self.stopped_at = tz_now()
        self.in_progress = False

    @property
    def duration(self) -> timedelta:
        if self.in_progress:
            return tz_now() - self.started_at
        return self.stopped_at - self.started_at

    @property
    def elapsed(self) -> float:
        return (self.duration).microseconds / 1e6
