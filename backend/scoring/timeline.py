"""Fast time-window lookups over sorted samples."""

from bisect import bisect_left, bisect_right
from collections.abc import Sequence
from typing import Generic, Protocol, TypeVar


class Timed(Protocol):
    t: float


T = TypeVar("T", bound=Timed)


class Timeline(Generic[T]):
    def __init__(self, items: Sequence[T]):
        self.items = sorted(items, key=lambda item: item.t)
        self._times = [item.t for item in self.items]

    def between(self, start: float, end: float) -> list[T]:
        """Items with start <= t <= end."""
        return self.items[bisect_left(self._times, start) : bisect_right(self._times, end)]

    def median_dt(self) -> float:
        if len(self._times) < 2:
            return 33.3
        gaps = sorted(b - a for a, b in zip(self._times, self._times[1:]) if b > a)
        return gaps[len(gaps) // 2] if gaps else 33.3
