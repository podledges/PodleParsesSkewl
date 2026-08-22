"""Teaching Report: lecture.present.html derived from a Lecture Document.

This is the local-core renderer the CLI and GUI call. It compresses Said into
teaching notes without inventing claims, applications, or diagrams. The
`/present` agent skill may then tighten mental models in the same HTML file.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path

from podleparsesskewl.document import LectureDocument, Still
from podleparsesskewl.errors import writing
from podleparsesskewl.timefmt import format_clock

PRESENT_NAME = "lecture.present.html"

_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_FILLER_START = re.compile(
    r"^(um+|uh+|okay|ok|so|right|well|anyway|alright)\b",
    re.IGNORECASE,
)
_APPLICATION = re.compile(
    r"\b(for example|e\.g\.|in practice|when you|you can|use this|"
    r"apply|real[- ]world|in the field|if you)\b",
    re.IGNORECASE,
)
_PITFALL = re.compile(
    r"\b(don't|do not|never|pitfall|common mistake|confused with|"
    r"mix(?:ed)? up|careful|watch out|instead of)\b",
    re.IGNORECASE,
)
_STEP = re.compile(r"\b(first|then|next|finally|step \d+)\b", re.IGNORECASE)

_STYLE = """
:root { color-scheme: light; }
body { font-family: Georgia, "Iowan Old Style", Palatino, serif; background: #f6f1e8; color: #1a1714;
  margin: 0; line-height: 1.55; }
.shell { max-width: 40rem; margin: 2.2rem auto; padding: 0 1.2rem 3rem; }
.hero, .panel, .topic { background: #fffaf1; border: 1px solid #ded4c6; box-shadow: 0 10px 28px rgba(51, 38, 25, 0.06); }
.hero { padding: 1.35rem 1.45rem; margin-bottom: 1rem; }
.panel, .topic { padding: 1.1rem 1.2rem; margin: 1rem 0; }
.eyebrow, .when, .meta, th, td, .label { font-family: "Segoe UI", system-ui, sans-serif; }
.eyebrow { letter-spacing: 0.08em; text-transform: uppercase; font-size: 0.72rem; color: #7a6a58; margin: 0; }
h1 { font-size: 1.85rem; margin: 0.35rem 0 0.6rem; font-weight: 600; }
h2 { font-size: 1.25rem; margin: 0 0 0.4rem; }
h3 { font-family: "Segoe UI", system-ui, sans-serif; font-size: 0.82rem; letter-spacing: 0.04em;
  text-transform: uppercase; color: #7a6a58; margin: 1.1rem 0 0.35rem; font-weight: 600; }
.meta, .when { color: #5c5348; font-size: 0.88rem; }
img.shown { width: 100%; height: auto; display: block; border: 1px solid #c9c0b4;
  box-shadow: 0 2px 8px rgba(40, 30, 20, 0.12); background: #efe8dc; margin: 0.6rem 0; }
hr { border: none; border-top: 1px solid #d8cfc2; margin: 1.35rem 0; }
.nutshell { font-size: 1.05rem; }
table { width: 100%; border-collapse: collapse; font-size: 0.9rem; margin: 0.6rem 0 0.2rem; }
th, td { text-align: left; padding: 0.35rem 0.45rem; border-bottom: 1px solid #e0d6c8; vertical-align: top; }
th { color: #7a6a58; font-weight: 600; }
pre.diagram { font-family: ui-monospace, Consolas, monospace; font-size: 0.82rem; white-space: pre-wrap;
  background: #efe8dc; border: 1px solid #d8cfc2; padding: 0.75rem 0.85rem; }
.said { white-space: pre-wrap; }
""".strip()


@dataclass(frozen=True)
class PresentResult:
    document: LectureDocument
    document_path: Path
    present_path: Path
    copy_problems: tuple[str, ...] = ()
    pairing_problems: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Topic:
    stills: tuple[Still, ...]
    said: str


def render_present(document: LectureDocument) -> str:
    """Build a self-contained teaching Report. Ground every claim in Said or Shown."""
    said_by_still = _said_by_still(document)
    topics = _topics(document, said_by_still)
    parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{html.escape(document.title)}</title>",
        f"<style>{_STYLE}</style>",
        "</head>",
        "<body>",
        '<main class="shell">',
        '<header class="hero">',
        '<p class="eyebrow">PodleParsesSkewl Teaching Report</p>',
        f"<h1>{html.escape(document.title)}</h1>",
        (
            f'<p class="meta">Duration {html.escape(format_clock(document.source.duration_seconds))}'
            f" · {len(topics)} topics · Transcript {html.escape(document.source.transcript_source)}</p>"
        ),
        "</header>",
        '<section class="panel">',
        "<h2>Executive summary</h2>",
        _executive_summary(topics),
        "</section>",
        '<section class="panel">',
        "<h2>Key concepts</h2>",
        _key_concepts(topics),
        "</section>",
        '<section class="panel">',
        "<h2>Timeline tied to Shown</h2>",
        _coverage_table(topics),
        "</section>",
    ]
    for index, topic in enumerate(topics, start=1):
        if index > 1:
            parts.append("<hr>")
        parts.append(_render_topic(index, topic))
    parts.append('<section class="panel">')
    parts.append("<h2>Review prompts</h2>")
    parts.append(_review_prompts(topics))
    parts.append("</section>")
    parts.extend(["</main>", "</body>", "</html>", ""])
    return "\n".join(parts)


def write_present(document: LectureDocument, output_dir: Path) -> Path:
    path = output_dir / PRESENT_NAME
    with writing(f"the teaching Report {path}"):
        output_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(render_present(document), encoding="utf-8")
    return path


def _said_by_still(document: LectureDocument) -> dict[str, str]:
    said: dict[str, str] = {}
    for section in document.sections:
        existing = said.get(section.still_id)
        if existing:
            said[section.still_id] = f"{existing} {section.said}".strip()
        else:
            said[section.still_id] = section.said
    return said


def _topics(document: LectureDocument, said_by_still: dict[str, str]) -> list[_Topic]:
    """Group a silent Still with the previous topic (typical progressive build)."""
    topics: list[_Topic] = []
    for still in document.stills:
        said = said_by_still.get(still.id, "").strip()
        if topics and not said:
            prev = topics[-1]
            topics[-1] = _Topic(stills=prev.stills + (still,), said=prev.said)
            continue
        topics.append(_Topic(stills=(still,), said=said))
    return topics or [_Topic(stills=document.stills, said="")]


def _executive_summary(topics: list[_Topic]) -> str:
    sentences: list[str] = []
    for topic in topics:
        topic_sentences = _sentences(topic.said)
        if topic_sentences:
            sentences.append(topic_sentences[0])
        if len(sentences) >= 3:
            break
    if not sentences:
        return "<p>The lecture is visual only here; use the Shown timeline below as the grounded outline.</p>"
    return f"<p>{html.escape(' '.join(sentences))}</p>"


def _key_concepts(topics: list[_Topic]) -> str:
    rows = ["<ul>"]
    any_concepts = False
    for index, topic in enumerate(topics, start=1):
        sentences = _sentences(topic.said)
        if not sentences:
            continue
        any_concepts = True
        rows.append(
            f"<li><strong>{html.escape(_heading(topic, index))}</strong> "
            f"<span class=\"when\">{html.escape(_topic_when(topic))}</span></li>"
        )
        if len(rows) >= 7:
            break
    if not any_concepts:
        rows.append("<li>No spoken concepts were captured for these Stills.</li>")
    rows.append("</ul>")
    return "\n".join(rows)


def _review_prompts(topics: list[_Topic]) -> str:
    prompts: list[str] = []
    for index, topic in enumerate(topics, start=1):
        sentences = _sentences(topic.said)
        if not sentences:
            continue
        prompts.append(
            f"In your own words, explain {html.escape(_heading(topic, index).lower())} "
            f"using {html.escape(', '.join(still.id for still in topic.stills))}."
        )
        applications = [item for item in sentences if _APPLICATION.search(item)]
        if applications:
            prompts.append(
                "What lecture-given use case makes this idea practical: "
                f"{html.escape(applications[0])}"
            )
        if len(prompts) >= 4:
            break
    if not prompts:
        return "<p>Use each Still to reconstruct what changed visually and what question it leaves.</p>"
    rows = ["<ul>"]
    for prompt in prompts:
        rows.append(f"<li>{prompt}</li>")
    rows.append("</ul>")
    return "\n".join(rows)


def _coverage_table(topics: list[_Topic]) -> str:
    rows = [
        "<table>",
        "<thead><tr><th>Topic</th><th>Time</th><th>Stills</th></tr></thead>",
        "<tbody>",
    ]
    for index, topic in enumerate(topics, start=1):
        heading = html.escape(_heading(topic, index))
        stills = ", ".join(still.id for still in topic.stills)
        rows.append(
            "<tr>"
            f"<td>{heading}</td>"
            f"<td>{html.escape(_topic_when(topic))}</td>"
            f"<td>{html.escape(stills)}</td>"
            "</tr>"
        )
    rows.extend(["</tbody>", "</table>"])
    return "\n".join(rows)


def _render_topic(index: int, topic: _Topic) -> str:
    sentences = _sentences(topic.said)
    heading = _heading(topic, index)
    nutshell = sentences[0] if sentences else "This Still was shown without spoken explanation."
    parts = [
        f'<section class="topic" id="topic-{index}">',
        f'<p class="eyebrow">Topic {index}</p>',
        f"<h2>{html.escape(heading)}</h2>",
        f'<p class="when">{html.escape(_topic_when(topic))}</p>',
        f'<p class="nutshell"><strong>In a nutshell.</strong> {html.escape(nutshell)}</p>',
    ]
    for still in topic.stills:
        if still.image:
            parts.append(
                f'<img class="shown" src="{html.escape(still.image)}" '
                f'alt="Shown for {html.escape(still.id)}">'
            )
            parts.append(f'<p class="when">{html.escape(still.id)} · {html.escape(_when(still))}</p>')
    if sentences:
        parts.append("<h3>Mental model</h3>")
        parts.append(
            f"<p>The lecture's own picture: {html.escape(sentences[0])} "
            "Treat this as a model of what was taught, not an extra claim.</p>"
        )
        rest = sentences[1:]
        parts.append("<h3>How it actually works</h3>")
        body = " ".join(rest) if rest else sentences[0]
        parts.append(f'<p class="said">{html.escape(body)}</p>')
        applications = [item for item in sentences if _APPLICATION.search(item)]
        if applications:
            parts.append("<h3>Where you would use this</h3>")
            parts.append("<ul>")
            for item in applications[:3]:
                parts.append(f"<li>{html.escape(item)}</li>")
            parts.append("</ul>")
        pitfalls = [item for item in sentences if _PITFALL.search(item)]
        if pitfalls:
            parts.append("<h3>Watch for</h3>")
            parts.append("<ul>")
            for item in pitfalls[:3]:
                parts.append(f"<li>{html.escape(item)}</li>")
            parts.append("</ul>")
        diagram = _ascii_steps(sentences)
        if diagram:
            parts.append("<h3>Diagram</h3>")
            parts.append(f'<pre class="diagram">{html.escape(diagram)}</pre>')
    else:
        parts.append("<h3>How it actually works</h3>")
        parts.append("<p>No spoken explanation was paired with this Shown.</p>")
    parts.append("</section>")
    return "\n".join(parts)


def _heading(topic: _Topic, index: int) -> str:
    first = _sentences(topic.said)
    if not first:
        return f"Shown {index}"
    text = first[0].rstrip(".")
    if len(text) > 72:
        text = text[:69].rsplit(" ", 1)[0]
    return text


def _topic_when(topic: _Topic) -> str:
    if not topic.stills:
        return "00:00:00 - 00:00:00"
    start = topic.stills[0].start_seconds
    end = topic.stills[-1].end_seconds
    return f"{format_clock(start)} - {format_clock(end)}"


def _when(still: Still) -> str:
    return f"{format_clock(still.start_seconds)} - {format_clock(still.end_seconds)}"


def _sentences(text: str) -> list[str]:
    chunks = [chunk.strip() for chunk in _SENTENCE.split(text.strip()) if chunk.strip()]
    if not chunks and text.strip():
        chunks = [text.strip()]
    cleaned: list[str] = []
    for chunk in chunks:
        piece = chunk.strip(" \t-")
        if not piece:
            continue
        if _FILLER_START.match(piece) and len(piece) < 24:
            continue
        cleaned.append(piece)
    return cleaned


def _ascii_steps(sentences: list[str]) -> str | None:
    stepped = [item for item in sentences if _STEP.search(item)]
    if len(stepped) < 2:
        return None
    lines = []
    for item in stepped[:6]:
        short = item if len(item) <= 88 else item[:85].rsplit(" ", 1)[0] + "..."
        lines.append(short)
    return " ->\n".join(lines)
