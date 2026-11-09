"""Plain human views of a Lecture Document: HTML and Markdown."""

from __future__ import annotations

import html
import math
from dataclasses import dataclass
from pathlib import Path

from podleparsesskewl.document import Cue, LectureDocument, Still
from podleparsesskewl.errors import PpsError, writing
from podleparsesskewl.timefmt import format_clock

DEFAULT_PAUSE_SECONDS = 1.5
DEFAULT_PARAGRAPH_WORDS = 120
TRANSCRIPT_NAME = "transcript.md"


@dataclass(frozen=True)
class TranscriptGroup:
    start_seconds: float
    end_seconds: float
    cue_indexes: tuple[int, ...]
    text: str


_HTML_STYLE = """
body { font-family: system-ui, sans-serif; max-width: 48rem; margin: 2rem auto; padding: 0 1rem; line-height: 1.5; color: #111; }
img.still { max-width: 100%; height: auto; display: block; background: #f4f4f4; }
hr { border: none; border-top: 1px solid #ccc; margin: 1.5rem 0; }
.when { color: #555; font-size: 0.9rem; }
.said { white-space: pre-wrap; }
.meta { color: #555; }
""".strip()


FAITHFUL_STYLE = """
.jumps { font-family: "Segoe UI", system-ui, sans-serif; font-size: 0.82rem; max-width: 40rem; margin: 1.4rem auto 0; padding: 0 1.2rem; }
.jumps a { color: #5c5348; }
.faithful { max-width: 40rem; margin: 0 auto 3rem; padding: 0 1.2rem 1rem; color: #1a1714;
  font-family: "Iowan Old Style", Palatino, Georgia, serif; line-height: 1.65; background: transparent; }
.faithful .eyebrow, .faithful .when { font-family: "Segoe UI", system-ui, sans-serif; }
.faithful .eyebrow { letter-spacing: 0.08em; text-transform: uppercase; font-size: 0.72rem; color: #7a6a58; margin: 1.6rem 0 0.3rem; }
.faithful h1 { font-size: 1.7rem; font-weight: 600; margin: 0.3rem 0 1.2rem; }
.faithful img.still { width: 100%; height: auto; display: block; border: 1px solid #c9c0b4;
  box-shadow: 0 2px 8px rgba(40, 30, 20, 0.12); background: #efe8dc; }
.faithful .when { color: #5c5348; font-size: 0.82rem; margin: 0.55rem 0 0.7rem; }
.faithful hr.rule { border: none; border-top: 1px solid #d8cfc2; margin: 0.7rem 0 0.9rem; }
.faithful hr.between { border: none; border-top: 2px solid #b9ae9f; margin: 2.6rem 0; }
.faithful .said p { margin: 0.35rem 0; white-space: pre-wrap; }
""".strip()


def render_faithful_fragment(document: LectureDocument) -> str:
    """Still-by-Still Shown and Said. Does not merge, drop, or rewrite Said.

    Paragraph breaks follow existing newlines only. Image ``src`` stays the
    Document's relative path so the folder remains portable.
    """
    said_by_still = _said_by_still(document)
    parts = [
        '<section id="shown-and-said" class="faithful">',
        '<p class="eyebrow">Shown and Said</p>',
        f"<h1>{html.escape(document.title)}</h1>",
    ]
    for index, still in enumerate(document.stills):
        if index:
            parts.append('<hr class="between">')
        parts.append(f'<section id="faithful-{html.escape(still.id)}">')
        parts.append(
            f'<img class="still" src="{html.escape(still.image, quote=True)}" '
            f'alt="Still {html.escape(str(still.index))}">'
        )
        parts.append(f'<p class="when">{html.escape(_when(still))}</p>')
        paragraphs = _said_paragraphs(said_by_still.get(still.id, ""))
        if paragraphs:
            parts.append('<hr class="rule">')
            parts.append(f'<div class="said">{paragraphs}</div>')
        parts.append("</section>")
    parts.append("</section>")
    return "\n".join(parts)


def render_faithful_html(document: LectureDocument) -> str:
    """Self-contained faithful review. Same constraints as the fragment."""
    return _html_page(document.title, FAITHFUL_STYLE, render_faithful_fragment(document))


def _html_page(title: str, style: str, body: str) -> str:
    return "\n".join([
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{html.escape(title)}</title>",
        f"<style>{style}</style>",
        "</head>",
        "<body>",
        body,
        "</body>",
        "</html>",
        "",
    ])


def _said_paragraphs(said: str) -> str:
    """Escape Said and break paragraphs on existing newlines. Do not rewrite it."""
    return "\n".join(f"<p>{html.escape(line)}</p>" for line in said.split("\n") if line != "")


def render_html(document: LectureDocument) -> str:
    """Render the plain program HTML view: Shown, separator, Said, per Still.

    A Still nobody spoke over keeps its separator from the next Still but drops
    the empty Said block, so the reader never meets two rules in a row.
    """
    parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{html.escape(document.title)}</title>",
        f"<style>{_HTML_STYLE}</style>",
        "</head>",
        "<body>",
        f"<h1>{html.escape(document.title)}</h1>",
        f'<p class="meta">Duration {html.escape(format_clock(document.source.duration_seconds))} · Transcript {html.escape(document.source.transcript_source)}</p>',
    ]
    said_by_still = _said_by_still(document)
    for index, still in enumerate(document.stills):
        said = said_by_still.get(still.id, "")
        if index > 0:
            parts.append("<hr>")
        parts.append(f'<section id="{html.escape(still.id)}">')
        parts.append(
            f'<img class="still" src="{html.escape(still.image)}" alt="Still {still.index}">'
        )
        parts.append(f'<p class="when">{html.escape(_when(still))}</p>')
        if said:
            parts.append("<hr>")
            parts.append(f'<div class="said">{html.escape(said)}</div>')
        parts.append("</section>")
    parts.extend(["</body>", "</html>", ""])
    return "\n".join(parts)


def render_markdown(document: LectureDocument) -> str:
    """Render a plain Markdown view with image, separator, then transcript."""
    lines = [
        f"# {document.title}",
        "",
        f"Duration {format_clock(document.source.duration_seconds)} · Transcript {document.source.transcript_source}",
        "",
    ]
    said_by_still = _said_by_still(document)
    for index, still in enumerate(document.stills):
        said = said_by_still.get(still.id, "")
        if index > 0:
            lines.append("---")
            lines.append("")
        lines.append(f"![Still {still.index}]({still.image})")
        lines.append("")
        lines.append(_when(still))
        lines.append("")
        if said:
            lines.append("---")
            lines.append("")
            lines.append(said)
            lines.append("")
    return "\n".join(lines)


def group_transcript(
    cues: tuple[Cue, ...],
    *,
    pause_seconds: float = DEFAULT_PAUSE_SECONDS,
    max_words: int = DEFAULT_PARAGRAPH_WORDS,
    visual_boundaries: tuple[float, ...] = (),
) -> tuple[TranscriptGroup, ...]:
    """Group faithful cues at pauses, visual boundaries, or a bounded size."""
    if pause_seconds < 0 or max_words < 1:
        raise PpsError("transcript pause seconds must be nonnegative and max words must be positive")
    groups: list[TranscriptGroup] = []
    indexes: list[int] = []
    words = 0
    previous: Cue | None = None
    boundaries = sorted(set(visual_boundaries))

    def finish() -> None:
        nonlocal indexes, words
        if not indexes:
            return
        selected = [cues[index] for index in indexes]
        groups.append(
            TranscriptGroup(
                start_seconds=selected[0].start_seconds,
                end_seconds=selected[-1].end_seconds,
                cue_indexes=tuple(indexes),
                text=" ".join(cue.text.strip() for cue in selected),
            )
        )
        indexes = []
        words = 0

    for index, cue in enumerate(cues):
        if (
            not math.isfinite(cue.start_seconds)
            or not math.isfinite(cue.end_seconds)
            or cue.start_seconds < 0
            or cue.end_seconds < cue.start_seconds
        ):
            raise PpsError(f"transcript cue {index} has invalid timing")
        if previous is not None and cue.start_seconds < previous.start_seconds:
            raise PpsError(f"transcript cue {index} starts before the preceding cue")
        cue_words = len(cue.text.split())
        pause = previous is not None and cue.start_seconds - previous.end_seconds >= pause_seconds
        visual = previous is not None and any(
            previous.start_seconds < boundary <= cue.start_seconds for boundary in boundaries
        )
        size = bool(indexes) and words + cue_words > max_words
        if pause or visual or size:
            finish()
        indexes.append(index)
        words += cue_words
        previous = cue
    finish()
    return tuple(groups)


def render_transcript_markdown(
    document: LectureDocument,
    *,
    pause_seconds: float = DEFAULT_PAUSE_SECONDS,
    max_words: int = DEFAULT_PARAGRAPH_WORDS,
) -> str:
    """Render every cue exactly once without rewriting or model-generated headings."""
    boundaries = tuple(still.start_seconds for still in document.stills[1:])
    groups = group_transcript(
        document.transcript.cues,
        pause_seconds=pause_seconds,
        max_words=max_words,
        visual_boundaries=boundaries,
    )
    lines = [
        f"# {document.title}",
        "",
        f"Duration {format_clock(document.source.duration_seconds)} · Transcript {document.source.transcript_source}",
        "",
    ]
    for group in groups:
        lines.extend([f"## {format_clock(group.start_seconds)}", "", group.text, ""])
    return "\n".join(lines)


def write_transcript_view(
    document: LectureDocument,
    output_dir: Path,
    *,
    pause_seconds: float = DEFAULT_PAUSE_SECONDS,
    max_words: int = DEFAULT_PARAGRAPH_WORDS,
) -> Path:
    path = output_dir / TRANSCRIPT_NAME
    with writing(f"the transcript Report {path}"):
        output_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(
            render_transcript_markdown(
                document,
                pause_seconds=pause_seconds,
                max_words=max_words,
            ),
            encoding="utf-8",
        )
    return path


def write_plain_views(document: LectureDocument, output_dir: Path) -> tuple[Path, Path]:
    html_path = output_dir / "lecture.html"
    md_path = output_dir / "lecture.md"
    with writing(f"the plain views in {output_dir}"):
        output_dir.mkdir(parents=True, exist_ok=True)
        html_path.write_text(render_html(document), encoding="utf-8")
        md_path.write_text(render_markdown(document), encoding="utf-8")
    return html_path, md_path


def pairing_problems(document: LectureDocument) -> list[str]:
    """Report Still/Section links that would quietly lose or duplicate Said."""
    problems: list[str] = []
    still_counts: dict[str, int] = {}
    for still in document.stills:
        still_counts[still.id] = still_counts.get(still.id, 0) + 1
        if still_counts[still.id] == 2:
            problems.append(
                f"still id {still.id!r} is claimed by more than one Still, so the same "
                "Said is shown under each of their images"
            )
    known = set(still_counts)
    counts: dict[str, int] = {}
    for section in document.sections:
        counts[section.still_id] = counts.get(section.still_id, 0) + 1
        if section.still_id not in known and counts[section.still_id] == 1:
            problems.append(
                f"section still_id {section.still_id!r} matches no Still, so its Said is "
                "left out of the rendered views"
            )
        elif section.still_id in known and counts[section.still_id] == 2:
            problems.append(
                f"still_id {section.still_id!r} is claimed by more than one section; "
                "their Said is joined in document order"
            )
    return problems


def _said_by_still(document: LectureDocument) -> dict[str, str]:
    """Honour the declared Section.still_id link rather than list position.

    Sections that share a still_id are joined in document order so no Said is
    dropped; `pairing_problems` reports the duplication.
    """
    said: dict[str, str] = {}
    for section in document.sections:
        existing = said.get(section.still_id)
        if existing:
            said[section.still_id] = f"{existing} {section.said}".strip()
        else:
            said[section.still_id] = section.said
    return said


def _when(still: Still) -> str:
    return f"{format_clock(still.start_seconds)} - {format_clock(still.end_seconds)}"
