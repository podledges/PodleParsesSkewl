"""Default lecture directory and lightweight user config."""

from __future__ import annotations

import os
import platform
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from podleparsesskewl.errors import PpsError

DEFAULT_LECTURES_DIR = r"C:\Users\ayden\Videos\Lectures"
ENV_LECTURES_DIR = "PODLEPARSESSKEWL_LECTURES_DIR"
CONFIG_NAME = "podleparsesskewl.toml"
_WINDOWS_DRIVE = re.compile(r"^([A-Za-z]):[\\/](.*)$")


@dataclass(frozen=True)
class AppConfig:
    lectures_dir: Path
    lectures_dir_source: str


def load_config(
    *,
    lectures_dir: Path | None = None,
    config_path: Path | None = None,
) -> AppConfig:
    """Resolve the lecture directory.

    Explicit beats ambient: `--lectures-dir`, then an explicit `--config` file,
    then the environment, then a discovered config file, then the default.
    """
    if lectures_dir is not None:
        return _config_for(str(lectures_dir), "flag")
    if config_path is not None:
        configured = _config_lectures_dir(config_path)
        if configured is not None:
            return _config_for(configured, f"config:{config_path}")
        return _config_for(DEFAULT_LECTURES_DIR, f"config:{config_path}")
    env = os.environ.get(ENV_LECTURES_DIR)
    if env:
        return _config_for(env, "env")
    found = _find_config()
    if found is not None:
        configured = _config_lectures_dir(found)
        if configured is not None:
            return _config_for(configured, f"config:{found}")
    return _config_for(DEFAULT_LECTURES_DIR, "default")


def running_under_wsl() -> bool:
    """True when this Linux process runs inside WSL, where C:\\ becomes /mnt/c."""
    if platform.system() != "Linux":
        return False
    release = platform.uname().release.lower()
    return "microsoft" in release or "wsl" in release


def windows_path_to_wsl(value: str) -> str | None:
    """Translate `C:\\Users\\...` to `/mnt/c/Users/...`; None if not a Windows path."""
    match = _WINDOWS_DRIVE.match(value.strip())
    if not match:
        return None
    drive, rest = match.groups()
    tail = rest.replace("\\", "/").strip("/")
    root = f"/mnt/{drive.lower()}"
    return f"{root}/{tail}" if tail else root


def _config_for(value: str, source: str) -> AppConfig:
    if running_under_wsl():
        translated = windows_path_to_wsl(value)
        if translated is not None:
            return AppConfig(
                lectures_dir=Path(translated),
                lectures_dir_source=f"{source} (WSL translation of {value})",
            )
    return AppConfig(lectures_dir=Path(value), lectures_dir_source=source)


def _config_lectures_dir(path: Path) -> str | None:
    payload = _read_toml(path)
    if "lectures_dir" not in payload:
        return None
    return str(payload["lectures_dir"])


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
