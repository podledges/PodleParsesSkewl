"""Plain human views of a Lecture Document: HTML and Markdown."""

from __future__ import annotations

import html
from pathlib import Path

from podleparsesskewl.document import LectureDocument, Still
from podleparsesskewl.timefmt import format_clock

_HTML_STYLE = """
body { font-family: system-ui, sans-serif; max-width: 48rem; margin: 2rem auto; padding: 0 1rem; line-height: 1.5; color: #111; }
img.still { max-width: 100%; height: auto; display: block; background: #f4f4f4; }
hr { border: none; border-top: 1px solid #ccc; margin: 1.5rem 0; }
.when { color: #555; font-size: 0.9rem; }
.said { white-space: pre-wrap; }
.meta { color: #555; }
""".strip()


def render_html(document: LectureDocument) -> str:
    """Render the plain program HTML view: Shown, separator, Said, per Still."""
    parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        f"<title>{html.escape(document.title)}</title>",
        f"<style>{_HTML_STYLE}</style>",
        "</head>",
        "<body>",
        f"<h1>{html.escape(document.title)}</h1>",
        f'<p class="meta">Duration {html.escape(format_clock(document.source.duration_seconds))} · Transcript {html.escape(document.source.transcript_source)}</p>',
    ]
    for index, still in enumerate(document.stills):
        section = document.sections[index] if index < len(document.sections) else None
        said = section.said if section is not None else ""
        if index > 0:
            parts.append("<hr>")
        parts.append(f'<section id="{html.escape(still.id)}">')
        parts.append(
            f'<img class="still" src="{html.escape(still.image)}" alt="Still {still.index}">'
        )
        parts.append(f'<p class="when">{html.escape(_when(still))}</p>')
        parts.append("<hr>")
        parts.append(f'<div class="said">{html.escape(said) if said else ""}</div>')
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
    for index, still in enumerate(document.stills):
        section = document.sections[index] if index < len(document.sections) else None
        said = section.said if section is not None else ""
        if index > 0:
            lines.append("---")
            lines.append("")
        lines.append(f"![Still {still.index}]({still.image})")
        lines.append("")
        lines.append(_when(still))
        lines.append("")
        lines.append("---")
        lines.append("")
        if said:
            lines.append(said)
            lines.append("")
    return "\n".join(lines)


def write_plain_views(document: LectureDocument, output_dir: Path) -> tuple[Path, Path]:
    html_path = output_dir / "lecture.html"
    md_path = output_dir / "lecture.md"
    html_path.write_text(render_html(document), encoding="utf-8")
    md_path.write_text(render_markdown(document), encoding="utf-8")
    return html_path, md_path


def _when(still: Still) -> str:
    return f"{format_clock(still.start_seconds)} - {format_clock(still.end_seconds)}"
