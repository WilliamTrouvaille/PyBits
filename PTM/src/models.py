"""Domain models and exceptions for PTM."""

from __future__ import annotations


class PTMError(Exception):
    """User-facing PTM error with a recovery hint."""

    def __init__(self, message: str, hint: str) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint
