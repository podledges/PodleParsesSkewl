"""User-facing errors for the CLI and pipeline."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator


class PpsError(Exception):
    """An error that should be printed without a traceback."""


@contextmanager
def writing(description: str) -> Iterator[None]:
    """Report a failed output write as a user-facing error, not a traceback."""
    try:
        yield
    except OSError as exc:
        raise PpsError(f"could not write {description}: {exc}") from exc
