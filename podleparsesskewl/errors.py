"""User-facing errors for the CLI and pipeline."""


class PpsError(Exception):
    """An error that should be printed without a traceback."""
