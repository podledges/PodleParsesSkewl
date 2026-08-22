"""Shared parse / present / parse+notes orchestration for CLI, GUI, and skills."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from podleparsesskewl.archive import ArchiveResult, archive_inputs
from podleparsesskewl.captions import discover_sidecar
from podleparsesskewl.config import AppConfig, lectures_dir_accessible, load_config
from podleparsesskewl.deps import Environment
from podleparsesskewl.errors import PpsError
from podleparsesskewl.present import PresentResult, write_present
from podleparsesskewl.report import pairing_problems
from podleparsesskewl.pipeline import (
    ParseOptions,
    ParseResult,
    copy_still_images,
    default_output_dir,
    load_document,
    parse_recording,
)

DOCUMENT_NAME = "lecture.json"


def build_parse_argv(recording: str, output: str = "", transcript: str = "") -> list[str]:
    """CLI arguments the GUI Parse button runs."""
    args = ["parse", recording]
    if output:
        args += ["--output", output]
    if transcript:
        args += ["--transcript", transcript]
    return args


def build_notes_argv(
    recording: str,
    output: str = "",
    transcript: str = "",
    archive_dir: str = "",
    archive: bool = True,
) -> list[str]:
    """CLI arguments the GUI Parse + Notes button runs."""
    args = ["notes", recording]
    if output:
        args += ["--output", output]
    if transcript:
        args += ["--transcript", transcript]
    if archive_dir:
        args += ["--archive-dir", archive_dir]
    if not archive:
        args.append("--no-archive")
    return args


def suggested_output_path(recording: str) -> str:
    if not recording.strip():
        return ""
    config = load_config()
    return str(resolve_output_dir(Path(recording), None, config))


def suggested_archive_path(recording: str = "") -> str:
    config = load_config()
    recording_path = Path(recording) if recording.strip() else None
    if (
        recording_path is None
        and config.archive_dir is None
        and not lectures_dir_accessible(config.lectures_dir)
    ):
        return ""
    return str(resolve_archive_dir(recording_path, None, config))


@dataclass(frozen=True)
class NotesRunResult:
    parse: ParseResult
    present: PresentResult
    archive: ArchiveResult | None
    recording: Path
    sidecar: Path | None
    output_dir: Path


def resolve_output_dir(
    recording: Path,
    output: Path | None = None,
    config: AppConfig | None = None,
) -> Path:
    """Choose this run's Lecture folder.

    An explicit output path is the folder itself. A configured default output
    directory is a parent; this Lecture is written to `<parent>/<stem>.lecture`.
    With neither, the folder sits next to the Recording as `<stem>.lecture`.
    """
    if output is not None:
        return output
    cfg = config if config is not None else load_config()
    if cfg.output_dir is not None:
        return cfg.output_dir / f"{recording.stem}.lecture"
    return default_output_dir(recording)


def resolve_archive_dir(
    recording: Path | None = None,
    archive_dir: Path | None = None,
    config: AppConfig | None = None,
) -> Path:
    """Choose the archive parent. Each run still gets its own unique subfolder."""
    if archive_dir is not None:
        return archive_dir
    cfg = config if config is not None else load_config()
    if cfg.archive_dir is not None:
        return cfg.archive_dir
    if recording is not None:
        return recording.resolve().parent / "archive"
    if lectures_dir_accessible(cfg.lectures_dir):
        return cfg.lectures_dir / "archive"
    return Path("archive")


def parse_lecture(
    recording: Path,
    *,
    output: Path | None = None,
    config: AppConfig | None = None,
    options: ParseOptions | None = None,
    env: Environment | None = None,
) -> ParseResult:
    cfg = config if config is not None else load_config()
    output_dir = resolve_output_dir(recording, output, cfg)
    parse_options = (
        ParseOptions(output_dir=output_dir)
        if options is None
        else replace(options, output_dir=output_dir)
    )
    return parse_recording(recording, parse_options, env=env)


def resolve_document_path(document: Path) -> Path:
    path = document
    if path.is_dir():
        candidate = path / DOCUMENT_NAME
        if candidate.is_file():
            return candidate
        raise PpsError(f"no {DOCUMENT_NAME} in folder {path}")
    if path.is_file():
        return path
    raise PpsError(f"Lecture Document not found: {path}")


def present_lecture(
    document_path: Path,
    *,
    output_dir: Path | None = None,
) -> PresentResult:
    source = resolve_document_path(document_path)
    document = load_document(source)
    target = output_dir if output_dir is not None else source.parent
    copy_problems: tuple[str, ...] = ()
    if target.resolve() != source.parent.resolve():
        copy_problems = tuple(copy_still_images(document, source.parent, target))
    problems = tuple(pairing_problems(document))
    present_path = write_present(document, target)
    return PresentResult(
        document=document,
        document_path=source,
        present_path=present_path,
        copy_problems=copy_problems,
        pairing_problems=problems,
    )


def parse_and_present(
    recording: Path,
    *,
    output: Path | None = None,
    config: AppConfig | None = None,
    options: ParseOptions | None = None,
    env: Environment | None = None,
    archive: bool | None = None,
    archive_dir: Path | None = None,
) -> NotesRunResult:
    """Parse one Recording, write teaching notes, then optionally archive inputs.

    Archive runs only after notes are written. A failed parse or present leaves
    the Recording where it was. A failed archive leaves the notes in place and
    raises, naming any files that did move.
    """
    cfg = config if config is not None else load_config()
    output_dir = resolve_output_dir(recording, output, cfg)
    sidecar = options.sidecar if options is not None and options.sidecar is not None else discover_sidecar(recording)
    parse_result = parse_lecture(
        recording,
        output=output_dir,
        config=cfg,
        options=options,
        env=env,
    )
    present_result = present_lecture(parse_result.document_path)
    should_archive = cfg.archive_after_notes if archive is None else archive
    archive_result = None
    if should_archive:
        dest = resolve_archive_dir(recording, archive_dir, cfg)
        archive_result = archive_inputs(
            archive_dir=dest,
            recording=recording,
            sidecar=sidecar,
            output_dir=parse_result.document_path.parent,
            result_paths={
                "document": str(parse_result.document_path),
                "html": str(parse_result.html_path),
                "markdown": str(parse_result.markdown_path),
                "present": str(present_result.present_path),
            },
            extra={
                "title": parse_result.document.title,
                "stills": len(parse_result.document.stills),
                "cues": len(parse_result.document.transcript.cues),
            },
        )
    return NotesRunResult(
        parse=parse_result,
        present=present_result,
        archive=archive_result,
        recording=recording,
        sidecar=sidecar,
        output_dir=output_dir,
    )
