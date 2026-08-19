"""Default lecture directory and lightweight user config."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from podleparsesskewl.errors import PpsError

DEFAULT_LECTURES_DIR = r"C:\Users\ayden\Videos\Lectures"
ENV_LECTURES_DIR = "PODLEPARSESSKEWL_LECTURES_DIR"
CONFIG_NAME = "podleparsesskewl.toml"


@dataclass(frozen=True)
class AppConfig:
    lectures_dir: Path
    lectures_dir_source: str


def load_config(
    *,
    lectures_dir: Path | None = None,
    config_path: Path | None = None,
) -> AppConfig:
    if lectures_dir is not None:
        return AppConfig(lectures_dir=lectures_dir, lectures_dir_source="flag")
    env = os.environ.get(ENV_LECTURES_DIR)
    if env:
        return AppConfig(lectures_dir=Path(env), lectures_dir_source="env")
    found = config_path or _find_config()
    if found is not None:
        payload = _read_toml(found)
        if "lectures_dir" in payload:
            return AppConfig(
                lectures_dir=Path(str(payload["lectures_dir"])),
                lectures_dir_source=f"config:{found}",
            )
    return AppConfig(
        lectures_dir=Path(DEFAULT_LECTURES_DIR),
        lectures_dir_source="default",
    )


def lectures_dir_accessible(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False


def list_recordings(directory: Path) -> list[Path]:
    if not lectures_dir_accessible(directory):
        return []
    found = [
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in {".mp4", ".m4v", ".mov"}
    ]
    return sorted(found, key=lambda path: path.stat().st_mtime, reverse=True)


def _find_config() -> Path | None:
    cwd = Path.cwd() / CONFIG_NAME
    if cwd.is_file():
        return cwd
    xdg = os.environ.get("XDG_CONFIG_HOME")
    home_config = Path(xdg) if xdg else Path.home() / ".config"
    candidate = home_config / "podleparsesskewl" / CONFIG_NAME
    if candidate.is_file():
        return candidate
    return None


def _read_toml(path: Path) -> dict:
    try:
        with path.open("rb") as handle:
            payload = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise PpsError(f"could not read config {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PpsError(f"config {path} must be a TOML table")
    return payload
