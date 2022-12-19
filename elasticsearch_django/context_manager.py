import time
from datetime import datetime


class stopwatch:
    def __enter__(self):
        self._start = time.time()
        return self

    def __exit__(self, type, value, traceback):
        self._stop = time.time()

    def started_at(self) -> datetime:
        return datetime.fromtimestamp(self._start)

    def stopped_at(self) -> datetime:
        return datetime.fromtimestamp(self._stop)

    def elapsed(self) -> float:
        return self._stop - self._start
