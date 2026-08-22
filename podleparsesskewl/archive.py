"""Move processed lecture inputs into a unique archive folder with a manifest."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from podleparsesskewl.errors import PpsError, writing

MANIFEST_NAME = "archive-manifest.json"
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class ArchiveResult:
    run_dir: Path
    manifest_path: Path
    moved: tuple[Path, ...]
    original_recording: str
    original_sidecar: str | None
    skipped: tuple[str, ...] = field(default_factory=tuple)


def unique_run_dir(archive_dir: Path, stem: str, when: datetime | None = None) -> Path:
    """Choose an empty archive folder. Never reuse a name that already exists."""
    stamp = (when or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    safe = _UNSAFE.sub("-", stem).strip(".-") or "lecture"
    base = archive_dir / f"{stamp}_{safe}"
    candidate = base
    suffix = 2
    while candidate.exists():
        candidate = archive_dir / f"{base.name}-{suffix}"
        suffix += 1
        if suffix > 1000:
            raise PpsError(f"could not allocate a unique archive folder under {archive_dir}")
    return candidate


def archive_inputs(
    *,
    archive_dir: Path,
    recording: Path,
    sidecar: Path | None,
    output_dir: Path,
    result_paths: dict[str, str],
    extra: dict | None = None,
    when: datetime | None = None,
) -> ArchiveResult:
    """Move the Recording (and sidecar) after a successful notes run.

    Copies nothing back. Creates a unique folder, refuses to overwrite, and
    writes a manifest of original and archived locations. If a move fails,
    already-moved files stay in the run folder and the error names them.
    """
    recording = recording.resolve()
    sidecar_resolved = sidecar.resolve() if sidecar is not None else None
    if not recording.is_file():
        raise PpsError(f"cannot archive; Recording is not a file: {recording}")
    if sidecar_resolved is not None and not sidecar_resolved.is_file():
        raise PpsError(f"cannot archive; transcript sidecar is not a file: {sidecar_resolved}")

    output_resolved = output_dir.resolve()
    generated_outputs = _generated_outputs(result_paths, output_resolved)
    to_move = _inputs_to_move(recording, sidecar_resolved, generated_outputs)
    if not to_move:
        raise PpsError("nothing to archive: no input files are safe to move")
    run_dir = unique_run_dir(archive_dir, recording.stem, when=when)
    with writing(f"the archive folder {run_dir}"):
        run_dir.mkdir(parents=True, exist_ok=False)

    moved: list[Path] = []
    try:
        for source in to_move:
            destination = run_dir / source.name
            if destination.exists():
                raise PpsError(
                    f"refusing to overwrite {destination}; archive folder already has that name"
                )
            _move_file(source, destination)
            moved.append(destination)
    except (OSError, PpsError) as exc:
        manifest_path = _write_manifest(
            run_dir,
            status="failed",
            recording=recording,
            sidecar=sidecar_resolved,
            output_dir=output_resolved,
            result_paths=result_paths,
            moved=moved,
            extra=extra,
            when=when,
            error="move interrupted; files already in the archive folder were not restored",
        )
        raise PpsError(
            f"archive move failed after placing {len(moved)} file(s) in {run_dir}. "
            f"See {manifest_path}. Originals that moved are no longer at their input paths."
        ) from exc

    skipped = _skip_reasons(recording, sidecar_resolved, generated_outputs, set(to_move))
    manifest_path = _write_manifest(
        run_dir,
        status="ok",
        recording=recording,
        sidecar=sidecar_resolved,
        output_dir=output_resolved,
        result_paths=result_paths,
        moved=moved,
        extra=extra,
        when=when,
        skipped=skipped,
    )
    return ArchiveResult(
        run_dir=run_dir,
        manifest_path=manifest_path,
        moved=tuple(moved),
        original_recording=str(recording),
        original_sidecar=str(sidecar_resolved) if sidecar_resolved else None,
        skipped=skipped,
    )


def _generated_outputs(result_paths: dict[str, str], output_dir: Path) -> set[Path]:
    generated = {
        output_dir / "lecture.json",
        output_dir / "lecture.present.html",
        output_dir / "lecture.ez.html",
    }
    for value in result_paths.values():
        if value:
            generated.add(Path(value).resolve())
    return {path.resolve() for path in generated}


def _inputs_to_move(
    recording: Path, sidecar: Path | None, generated_outputs: set[Path]
) -> list[Path]:
    items = [recording]
    if sidecar is not None and sidecar != recording:
        items.append(sidecar)
    return [path for path in items if path.resolve() not in generated_outputs]


def _skip_reasons(
    recording: Path,
    sidecar: Path | None,
    generated_outputs: set[Path],
    moved_sources: set[Path],
) -> tuple[str, ...]:
    reasons: list[str] = []
    if sidecar is not None and sidecar not in moved_sources:
        if sidecar.resolve() in generated_outputs:
            reasons.append(
                f"left generated output in place instead of archiving it: {sidecar}"
            )
        elif sidecar == recording:
            reasons.append("sidecar path is the Recording itself")
        else:
            reasons.append(f"sidecar was not moved: {sidecar}")
    if recording not in moved_sources:
        if recording.resolve() in generated_outputs:
            reasons.append(
                f"left generated output in place instead of archiving it: {recording}"
            )
        else:
            reasons.append(f"Recording was not moved: {recording}")
    return tuple(reasons)


def _move_file(source: Path, destination: Path) -> None:
    with writing(f"archived file {destination}"):
        shutil.move(str(source), str(destination))
        if source.exists():
            raise PpsError(
                f"archive move left the original in place at {source} after writing {destination}"
            )
        if not destination.is_file():
            raise PpsError(f"archive move did not produce a file at {destination}")


def _write_manifest(
    run_dir: Path,
    *,
    status: str,
    recording: Path,
    sidecar: Path | None,
    output_dir: Path,
    result_paths: dict[str, str],
    moved: list[Path],
    extra: dict | None,
    when: datetime | None,
    skipped: tuple[str, ...] = (),
    error: str | None = None,
) -> Path:
    stamp = (when or datetime.now(timezone.utc)).astimezone(timezone.utc)
    archived_recording = next(
        (str(path) for path in moved if path.name == recording.name), None
    )
    archived_sidecar = None
    if sidecar is not None:
        archived_sidecar = next(
            (str(path) for path in moved if path.name == sidecar.name), None
        )
    payload = {
        "archived_at": stamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": status,
        "input": {
            "original_recording": str(recording),
            "original_sidecar": str(sidecar) if sidecar is not None else None,
            "archived_recording": archived_recording,
            "archived_sidecar": archived_sidecar,
        },
        "output": {
            "directory": str(output_dir),
            **result_paths,
        },
        "moved": [str(path) for path in moved],
        "skipped": list(skipped),
    }
    if extra:
        payload["result"] = extra
    if error:
        payload["error"] = error
    path = run_dir / MANIFEST_NAME
    with writing(f"the archive manifest {path}"):
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
