"""Command-line surface for doctor, list, parse, and render."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from podleparsesskewl import __version__
from podleparsesskewl.config import (
    DEFAULT_LECTURES_DIR,
    AppConfig,
    lectures_dir_accessible,
    list_recordings,
    load_config,
)
from podleparsesskewl.deps import format_doctor, inspect_environment
from podleparsesskewl.errors import PpsError, writing
from podleparsesskewl.pipeline import (
    ParseOptions,
    copy_still_images,
    default_output_dir,
    load_document,
    parse_recording,
)
from podleparsesskewl.report import section_problems, write_plain_views
from podleparsesskewl.stills import DEFAULT_CHANGE_RATIO, DEFAULT_MIN_HOLD_SECONDS, DEFAULT_SAMPLE_FPS


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            return _cmd_doctor(args)
        if args.command == "list":
            return _cmd_list(args)
        if args.command == "parse":
            return _cmd_parse(args)
        if args.command == "render":
            return _cmd_render(args)
        parser.print_help()
        return 2
    except PpsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pps",
        description="Review reconstruction: pair what was said with what was shown in a lecture MP4.",
    )
    parser.add_argument("--version", action="version", version=f"podleparsesskewl {__version__}")
    sub = parser.add_subparsers(dest="command")

    doctor = sub.add_parser("doctor", help="check ffmpeg, transcription engines, and lecture directory")
    _add_config_flags(doctor)

    listing = sub.add_parser("list", help="list Recordings in the lecture directory")
    _add_config_flags(listing)
    listing.add_argument(
        "directory",
        nargs="?",
        type=Path,
        help="directory to list (defaults to the configured lecture directory)",
    )

    parse = sub.add_parser("parse", help="process one MP4 into a Lecture Document and plain HTML")
    _add_config_flags(parse)
    parse.add_argument(
        "recording",
        nargs="?",
        type=Path,
        help="path to an MP4 Recording (omit with --latest)",
    )
    parse.add_argument(
        "--latest",
        action="store_true",
        help="use the newest MP4 in the configured lecture directory",
    )
    parse.add_argument(
        "-o",
        "--output",
        type=Path,
        help="output directory (default: <recording>.lecture/ next to the file)",
    )
    parse.add_argument("--title", help="Lecture title (default: recording filename)")
    parse.add_argument(
        "--transcript",
        type=Path,
        help="caption sidecar (.srt, .vtt, or .json) instead of auto-discovery",
    )
    parse.add_argument("--sample-fps", type=float, default=DEFAULT_SAMPLE_FPS)
    parse.add_argument("--change-ratio", type=float, default=DEFAULT_CHANGE_RATIO)
    parse.add_argument("--min-hold-seconds", type=float, default=DEFAULT_MIN_HOLD_SECONDS)
    parse.add_argument(
        "--keep-work",
        action="store_true",
        help="keep this run's intermediate ffmpeg files in its _work-* folder under the output directory",
    )

    render = sub.add_parser("render", help="rebuild plain HTML/Markdown from lecture.json")
    render.add_argument("document", type=Path, help="path to lecture.json")
    render.add_argument(
        "-o",
        "--output",
        type=Path,
        help="output directory (default: the document's parent)",
    )
    return parser


def _add_config_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--lectures-dir",
        type=Path,
        help=f"lecture directory (default: {DEFAULT_LECTURES_DIR})",
    )
    parser.add_argument("--config", type=Path, help="TOML config file")


def _cmd_doctor(args: argparse.Namespace) -> int:
    env = inspect_environment()
    print(format_doctor(env))
    config = _config_from_args(args)
    accessible = lectures_dir_accessible(config.lectures_dir)
    print("Lecture directory")
    print(f"  path         {config.lectures_dir}")
    print(f"  source       {config.lectures_dir_source}")
    print(f"  accessible   {'yes' if accessible else 'no'}")
    if not accessible:
        print()
        print(
            "This machine cannot see the configured lecture directory. "
            "Pass a Recording path to `pps parse`, copy MP4 files here, or set "
            "PODLEPARSESSKEWL_LECTURES_DIR. Agents may retrieve files from "
            f"{DEFAULT_LECTURES_DIR} on the captain's Windows machine."
        )
    return 0 if env.can_parse_video else 1


def _cmd_list(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    directory = args.directory if args.directory is not None else config.lectures_dir
    if not lectures_dir_accessible(directory):
        raise PpsError(
            f"lecture directory is not accessible: {directory}. "
            "Pass a local path, or have an agent copy files from "
            f"{DEFAULT_LECTURES_DIR}."
        )
    recordings = list_recordings(directory)
    if not recordings:
        print(f"no Recordings found in {directory}")
        return 0
    for path in recordings:
        print(path)
    return 0


def _cmd_parse(args: argparse.Namespace) -> int:
    recording = _resolve_recording(args)
    output = args.output if args.output is not None else default_output_dir(recording)
    result = parse_recording(
        recording,
        ParseOptions(
            output_dir=output,
            title=args.title,
            sidecar=args.transcript,
            sample_fps=args.sample_fps,
            change_ratio=args.change_ratio,
            min_hold_seconds=args.min_hold_seconds,
            keep_work=args.keep_work,
        ),
    )
    print(f"Document  {result.document_path}")
    print(f"HTML      {result.html_path}")
    print(f"Markdown  {result.markdown_path}")
    print(f"Stills    {len(result.document.stills)}")
    print(f"Cues      {len(result.document.transcript.cues)}")
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    document = load_document(args.document)
    source_dir = args.document.parent
    output = args.output if args.output is not None else source_dir
    with writing(f"the output folder {output}"):
        output.mkdir(parents=True, exist_ok=True)
    relocated = output.resolve() != source_dir.resolve()
    if relocated:
        problems = copy_still_images(document, source_dir, output)
        with writing(f"the Lecture Document in {output}"):
            shutil.copyfile(args.document, output / "lecture.json")
        for problem in problems:
            print(f"warning: {problem}", file=sys.stderr)
    for problem in section_problems(document):
        print(f"warning: {problem}", file=sys.stderr)
    html_path, md_path = write_plain_views(document, output)
    print(f"HTML      {html_path}")
    print(f"Markdown  {md_path}")
    return 0


def _resolve_recording(args: argparse.Namespace) -> Path:
    if args.recording is not None:
        return args.recording
    if not args.latest:
        raise PpsError("pass a Recording path, or use --latest with an accessible lecture directory")
    config = _config_from_args(args)
    if not lectures_dir_accessible(config.lectures_dir):
        raise PpsError(
            f"cannot use --latest; lecture directory is not accessible: {config.lectures_dir}. "
            f"Copy an MP4 locally, or retrieve files from {DEFAULT_LECTURES_DIR}."
        )
    recordings = list_recordings(config.lectures_dir)
    if not recordings:
        raise PpsError(f"no Recordings found in {config.lectures_dir}")
    return recordings[0]


def _config_from_args(args: argparse.Namespace) -> AppConfig:
    return load_config(
        lectures_dir=getattr(args, "lectures_dir", None),
        config_path=getattr(args, "config", None),
    )
