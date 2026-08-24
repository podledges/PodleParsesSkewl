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
ENV_OUTPUT_DIR = "PODLEPARSESSKEWL_OUTPUT_DIR"
ENV_ARCHIVE_DIR = "PODLEPARSESSKEWL_ARCHIVE_DIR"
CONFIG_NAME = "podleparsesskewl.toml"
_WINDOWS_DRIVE = re.compile(r"^([A-Za-z]):[\\/](.*)$")


@dataclass(frozen=True)
class AppConfig:
    lectures_dir: Path
    lectures_dir_source: str
    output_dir: Path | None = None
    output_dir_source: str = "unset"
    archive_dir: Path | None = None
    archive_dir_source: str = "unset"
    archive_after_notes: bool = True


def load_config(
    *,
    lectures_dir: Path | None = None,
    output_dir: Path | None = None,
    archive_dir: Path | None = None,
    config_path: Path | None = None,
) -> AppConfig:
    """Resolve lecture, default-output, and archive directories.

    Explicit beats ambient, per key: a flag, then an explicit `--config` file,
    then the environment, then a discovered config file, then the default.
    An explicit `--config` file does not fall back to the environment.
    """
    if config_path is not None:
        file_payload = _read_toml(config_path)
        file_source = f"config:{config_path}"
        use_env = False
    else:
        found = _find_config()
        file_payload = _read_toml(found) if found is not None else {}
        file_source = f"config:{found}" if found is not None else ""
        use_env = True

    lectures_value, lectures_source = _resolve_required_path(
        flag=lectures_dir,
        env_name=ENV_LECTURES_DIR,
        file_value=_toml_string(file_payload, "lectures_dir"),
        file_source=file_source,
        default=DEFAULT_LECTURES_DIR,
        use_env=use_env,
    )
    output_value, output_source = _resolve_optional_path(
        flag=output_dir,
        env_name=ENV_OUTPUT_DIR,
        file_value=_toml_string(file_payload, "output_dir"),
        file_source=file_source,
        use_env=use_env,
    )
    archive_value, archive_source = _resolve_optional_path(
        flag=archive_dir,
        env_name=ENV_ARCHIVE_DIR,
        file_value=_toml_string(file_payload, "archive_dir"),
        file_source=file_source,
        use_env=use_env,
    )
    archive_after = _toml_bool(file_payload, "archive_after_notes", True)
    lectures_path, lectures_label = _maybe_translate(lectures_value, lectures_source)
    output_path, output_label = (
        _maybe_translate(output_value, output_source) if output_value else (None, "unset")
    )
    archive_path, archive_label = (
        _maybe_translate(archive_value, archive_source) if archive_value else (None, "unset")
    )
    return AppConfig(
        lectures_dir=lectures_path,
        lectures_dir_source=lectures_label,
        output_dir=output_path,
        output_dir_source=output_label,
        archive_dir=archive_path,
        archive_dir_source=archive_label,
        archive_after_notes=archive_after,
    )


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


def _resolve_required_path(
    *,
    flag: Path | None,
    env_name: str,
    file_value: str | None,
    file_source: str,
    default: str,
    use_env: bool,
) -> tuple[str, str]:
    if flag is not None:
        return str(flag), "flag"
    if not use_env:
        if file_value is not None:
            return file_value, file_source
        return default, file_source or "default"
    env = os.environ.get(env_name)
    if env:
        return env, "env"
    if file_value is not None:
        return file_value, file_source
    return default, "default"


def _resolve_optional_path(
    *,
    flag: Path | None,
    env_name: str,
    file_value: str | None,
    file_source: str,
    use_env: bool,
) -> tuple[str | None, str]:
    if flag is not None:
        return str(flag), "flag"
    if not use_env:
        if file_value is not None:
            return file_value, file_source
        return None, "unset"
    env = os.environ.get(env_name)
    if env:
        return env, "env"
    if file_value is not None:
        return file_value, file_source
    return None, "unset"


def _maybe_translate(value: str, source: str) -> tuple[Path, str]:
    if running_under_wsl():
        translated = windows_path_to_wsl(value)
        if translated is not None:
            return Path(translated), f"{source} (WSL translation of {value})"
    return Path(value), source


def _toml_string(payload: dict, key: str) -> str | None:
    if key not in payload:
        return None
    value = payload[key]
    if not isinstance(value, str) or not value.strip():
        raise PpsError(f"config {key} must be a non-empty string")
    return value


def _toml_bool(payload: dict, key: str, default: bool) -> bool:
    if key not in payload:
        return default
    value = payload[key]
    if not isinstance(value, bool):
        raise PpsError(f"config {key} must be true or false")
    return value


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
