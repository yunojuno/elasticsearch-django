from __future__ import annotations

import time
from datetime import datetime
from types import TracebackType


class stopwatch:
    def __enter__(self) -> stopwatch:
        self._start = time.time()
        return self

    def __exit__(
        self,
        exc_type: type[Exception],
        exc_value: Exception,
        traceback: TracebackType,
    ) -> None:
        self._stop = time.time()

    @property
    def started_at(self) -> datetime:
        return datetime.fromtimestamp(self._start)

    @property
    def stopped_at(self) -> datetime:
        return datetime.fromtimestamp(self._stop)

    @property
    def elapsed(self) -> float:
        return self._stop - self._start
