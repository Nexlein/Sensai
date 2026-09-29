"""Data types shared by the PII rules and the detector."""

import re
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class PiiRule:
    name: str
    pattern: re.Pattern[str]
    replacement: str
    validator: Callable[[str], bool] | None = None
    # Called with a match that failed `validator`: returns the (start, end) of a
    # valid part inside it, if any.
    recover: Callable[[str], tuple[int, int] | None] | None = None


@dataclass(frozen=True)
class PiiMatch:
    rule: str
    start: int
    end: int
    replacement: str
