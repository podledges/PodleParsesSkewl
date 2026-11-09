"""Per-Still timing signal, sliding windows, and grade validation.

Stage 1 is deterministic and runs inside every parse. Same-page identity
(appearance) is grouped at parse time with stills.DEFAULT_CHANGE_RATIO;
this module only reads Still.appearance.
"""

from __future__ import annotations

import json
import math
import re
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from podleparsesskewl.document import Cue, LectureDocument, Still, finite_seconds
from podleparsesskewl.errors import PpsError, writing
from podleparsesskewl.report import DEFAULT_PAUSE_SECONDS
from podleparsesskewl.stills import DEFAULT_CHANGE_RATIO
from podleparsesskewl.timefmt import format_clock

APPEARANCE_CHANGE_RATIO = DEFAULT_CHANGE_RATIO

SIGNAL_SCHEMA = "podleparsesskewl.signal/v1"
STILLS_TEXT_SCHEMA = "podleparsesskewl.stills-text/v1"
GRADES_SCHEMA = "podleparsesskewl.grades/v1"

SIGNAL_JSON = "lecture.signal.json"
SIGNAL_MD = "lecture.signal.md"
STILLS_TEXT_NAME = "lecture.stills-text.json"
GRADES_JSON = "lecture.grades.json"
BRIEF_NAME = "lecture.brief.md"
TAUGHT_NAME = "lecture.taught.md"

PAUSE_SECONDS = DEFAULT_PAUSE_SECONDS
DEAD_AIR_SECONDS = 2.0
MIN_WORDS_PER_SECOND = 0.5
PASS_THROUGH_SECONDS = 3.0
BOILERPLATE_SPOKEN_SECONDS = 3.0
PRESCORE_ZERO_SPOKEN_SECONDS = 5.0
TANGENT_SPOKEN_SECONDS = 45.0
TANGENT_OVERLAP = 0.15
FLUFF_SPOKEN_SECONDS = 30.0
WINDOW_SIZE = 8
WINDOW_STRIDE = 4
HIGH_DENSITY_QUANTILE = 0.75
MIN_TOKEN_CHARS = 3
BAR_WIDTH = 40
EXCERPT_WORDS = 12
EXCERPT_CHARS = 120

FILLER_TAGS = (
    "music",
    "silence",
    "inaudible",
    "applause",
    "noise",
    "laughter",
    "blank_audio",
)
EMPHASIS_PHRASES = (
    "exam",
    "exams",
    "test",
    "quiz",
    "derive",
    "derivation",
    "crucial",
    "common mistake",
    "understand why",
    "trick",
    "important",
    "will be on the",
    "make sure you can",
    "remember",
    "key point",
    "pay attention",
)
STOPWORDS = frozenset(
    """
    a an the and or but if then else when while although because as of at by for
    with about against between into through during before after above below to
    from up down in out on off over under again further once here there where
    why how all any both each few more most other some such no nor not only own
    same so than too very can will just should now i me my we our you your he
    him his she her it its they them their this that these those am is are was
    were be been being have has had having do does did doing would could might
    must shall okay right like thing things going get got yeah um uh also well
    really actually basically literally maybe perhaps something anything
    everything nothing someone anyone everyone whatever however therefore thus
    hence still already always never often sometimes usually quite rather even
    much many lot lots
    """.split()
)
ADMIN_TITLE = re.compile(
    r"^\s*(title|agenda|outline|overview|contents?|break|q\s*&\s*a|questions?|"
    r"references?|bibliography|thank you|thanks|end|summary|recap|administrivia|"
    r"announcements?|housekeeping)\b",
    re.I,
)
_TAG_GROUPS = re.compile(r"\[.*?\]|\(.*?\)")
_EMPHASIS_PATTERNS = tuple(
    (
        phrase,
        re.compile(
            r"\b" + re.escape(phrase).replace(r"\ ", r"\s+") + r"\b",
            re.I,
        ),
    )
    for phrase in EMPHASIS_PHRASES
)
_RAW_STILL = frozenset({"elapsed_raw", "spoken_raw"})
_RAW_WINDOW = frozenset({"spoken_raw_total", "mean_raw"})
IMPORTANCE_CATEGORY = {
    0: "noise_admin_or_tangent",
    1: "low_yield_context",
    2: "core_testable_concept",
    3: "critical_exam_skill",
}


@dataclass(frozen=True)
class StillText:
    title: str
    text: str
    has_diagram: bool


@dataclass(frozen=True)
class SignalThresholds:
    pause_seconds: float = PAUSE_SECONDS
    dead_air_seconds: float = DEAD_AIR_SECONDS
    min_words_per_second: float = MIN_WORDS_PER_SECOND
    pass_through_seconds: float = PASS_THROUGH_SECONDS
    boilerplate_spoken_seconds: float = BOILERPLATE_SPOKEN_SECONDS
    prescore_zero_spoken_seconds: float = PRESCORE_ZERO_SPOKEN_SECONDS
    tangent_spoken_seconds: float = TANGENT_SPOKEN_SECONDS
    tangent_overlap: float = TANGENT_OVERLAP
    fluff_spoken_seconds: float = FLUFF_SPOKEN_SECONDS
    window_size: int = WINDOW_SIZE
    window_stride: int = WINDOW_STRIDE
    high_density_quantile: float = HIGH_DENSITY_QUANTILE
    min_token_chars: int = MIN_TOKEN_CHARS

    def validate(self) -> None:
        if self.pause_seconds < 0:
            raise PpsError("--pause-seconds must be >= 0")
        if self.dead_air_seconds < self.pause_seconds:
            raise PpsError("dead_air_seconds must be >= pause_seconds")
        if self.min_words_per_second < 0:
            raise PpsError("min_words_per_second must be >= 0")
        if self.pass_through_seconds < 0:
            raise PpsError("--pass-through-seconds must be >= 0")
        if self.window_size < 1:
            raise PpsError("--window-size must be >= 1")
        if not 1 <= self.window_stride <= self.window_size:
            raise PpsError("--window-stride must be between 1 and --window-size")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "pause_seconds": self.pause_seconds,
            "dead_air_seconds": self.dead_air_seconds,
            "min_words_per_second": self.min_words_per_second,
            "pass_through_seconds": self.pass_through_seconds,
            "boilerplate_spoken_seconds": self.boilerplate_spoken_seconds,
            "prescore_zero_spoken_seconds": self.prescore_zero_spoken_seconds,
            "tangent_spoken_seconds": self.tangent_spoken_seconds,
            "tangent_overlap": self.tangent_overlap,
            "fluff_spoken_seconds": self.fluff_spoken_seconds,
            "window_size": self.window_size,
            "window_stride": self.window_stride,
            "high_density_quantile": self.high_density_quantile,
            "min_token_chars": self.min_token_chars,
        }

    @classmethod
    def from_json_dict(cls, payload: Any) -> SignalThresholds:
        if not isinstance(payload, dict):
            raise PpsError("signal thresholds must be a JSON object")
        known = {field: payload[field] for field in cls.__dataclass_fields__ if field in payload}
        for name, value in known.items():
            expected = (int,) if cls.__dataclass_fields__[name].type == "int" else (int, float)
            if isinstance(value, bool) or not isinstance(value, expected):
                kind = "an integer" if expected == (int,) else "a number"
                raise PpsError(f"invalid signal thresholds: {name} must be {kind}")
        try:
            thresholds = cls(**known)
            thresholds.validate()
        except (TypeError, ValueError) as exc:
            raise PpsError(f"invalid signal thresholds: {exc}") from exc
        return thresholds


@dataclass(frozen=True)
class ComputedSignal:
    payload: dict[str, Any]
    stills: list[dict[str, Any]]
    windows: list[dict[str, Any]]

    def to_json_dict(self) -> dict[str, Any]:
        return self.payload


def round_half_up(value: float) -> int:
    """Round a non-negative number to the nearest integer; halves go up."""
    if value < 0:
        raise PpsError(f"round_half_up expects a non-negative number, got {value!r}")
    return math.floor(value + 0.5)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def tokenize(text: str, *, min_chars: int = MIN_TOKEN_CHARS) -> list[str]:
    parts = re.split(r"[^0-9a-z]+", text.casefold())
    return [part for part in parts if part and part not in STOPWORDS and len(part) >= min_chars]


def _without_tags(text: str) -> str:
    return _TAG_GROUPS.sub(" ", text).replace("♪", " ")


def cue_is_noise(cue: Cue, min_words_per_second: float = MIN_WORDS_PER_SECOND) -> bool:
    if not cue.text.strip():
        return True
    tokens = _without_tags(cue.text).split()
    if not any(any(char.isalnum() for char in token) for token in tokens):
        return True
    duration = cue.end_seconds - cue.start_seconds
    if duration > 0 and (len(tokens) / duration) < min_words_per_second:
        return True
    return False


def cue_word_count(cue: Cue) -> int:
    return len(_without_tags(cue.text).split())


def window_bounds(count: int, size: int, stride: int) -> list[tuple[int, int]]:
    """Inclusive 1-based window ranges, dropping a window contained in the previous."""
    if count <= 0:
        return []
    bounds: list[tuple[int, int]] = []
    start = 1
    while start <= count:
        last = min(start + size - 1, count)
        if bounds:
            prev_start, prev_last = bounds[-1]
            if start >= prev_start and last <= prev_last:
                start += stride
                continue
        bounds.append((start, last))
        start += stride
    return bounds


def load_stills_text(path: Path, known_ids: Iterable[str]) -> dict[str, StillText]:
    known = set(known_ids)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PpsError(f"could not read Still text sidecar {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PpsError(f"Still text sidecar {path} must be a JSON object")
    schema = payload.get("schema")
    if schema != STILLS_TEXT_SCHEMA:
        raise PpsError(
            f"Still text sidecar {path} has schema {schema!r}, expected {STILLS_TEXT_SCHEMA}"
        )
    if "stills" not in payload:
        raise PpsError(f"Still text sidecar {path} is missing the required field 'stills'")
    raw_stills = payload["stills"]
    if not isinstance(raw_stills, dict):
        raise PpsError(f"Still text sidecar {path} field stills must be an object")
    result: dict[str, StillText] = {}
    for still_id, item in raw_stills.items():
        if still_id not in known:
            raise PpsError(f"Still text sidecar names unknown Still id {still_id}")
        if not isinstance(item, dict):
            raise PpsError(f"Still text sidecar {still_id} must be an object")
        title = item.get("title", "")
        text = item.get("text", "")
        has_diagram = item.get("has_diagram")
        if not isinstance(title, str):
            raise PpsError(f"Still text sidecar {still_id} title must be text")
        if not isinstance(text, str):
            raise PpsError(f"Still text sidecar {still_id} text must be text")
        if not isinstance(has_diagram, bool):
            raise PpsError(f"Still text sidecar {still_id} has_diagram must be a boolean")
        result[still_id] = StillText(title=title, text=text, has_diagram=has_diagram)
    return result


def load_signal(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PpsError(f"could not read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PpsError(f"{path} must be a JSON object")
    return payload


def load_grades(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PpsError(f"could not read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PpsError(f"{path} must be a JSON object")
    return payload


def compute_signal(
    document: LectureDocument,
    stills_text: dict[str, StillText] | None = None,
    thresholds: SignalThresholds | None = None,
    *,
    generated_at: str | None = None,
) -> ComputedSignal:
    options = thresholds or SignalThresholds()
    options.validate()
    appearance_recorded = bool(document.stills) and all(
        still.appearance is not None for still in document.stills
    )
    covered = 0
    if stills_text:
        covered = sum(1 for still in document.stills if still.id in stills_text)
    inputs = {
        "appearance_recorded": appearance_recorded,
        "stills_text": {
            "present": stills_text is not None,
            "covered": covered,
            "of": len(document.stills),
        },
    }
    cues = document.transcript.cues
    sections_by_still: dict[str, list] = {still.id: [] for still in document.stills}
    for section in document.sections:
        sections_by_still.setdefault(section.still_id, []).append(section)

    still_rows: list[dict[str, Any]] = []
    for still in document.stills:
        finite_seconds(still.start_seconds, f"{still.id}.start_seconds")
        finite_seconds(still.end_seconds, f"{still.id}.end_seconds")
        still_rows.append(
            _measure_still(
                still,
                sections_by_still.get(still.id, []),
                cues,
                stills_text,
                options,
            )
        )
    visits = _visit_fields(document.stills, still_rows, appearance_recorded)
    for row in still_rows:
        row.update(visits[row["still_id"]])

    windows = _measure_windows(still_rows, options)
    summary = _summary(document, still_rows, windows, appearance_recorded)
    payload = {
        "schema": SIGNAL_SCHEMA,
        "document": "lecture.json",
        "title": document.title,
        "duration_seconds": document.source.duration_seconds,
        "generated_at": generated_at or utc_now(),
        "inputs": inputs,
        "thresholds": options.to_json_dict(),
        "stills": [_without_keys(row, _RAW_STILL) for row in still_rows],
        "windows": [_without_keys(row, _RAW_WINDOW) for row in windows],
        "summary": summary,
    }
    return ComputedSignal(payload=payload, stills=still_rows, windows=windows)


def write_signal_views(
    document: LectureDocument,
    output_dir: Path,
    stills_text: dict[str, StillText] | None = None,
    thresholds: SignalThresholds | None = None,
) -> tuple[Path, Path]:
    computed = compute_signal(document, stills_text, thresholds)
    json_path = output_dir / SIGNAL_JSON
    md_path = output_dir / SIGNAL_MD
    try:
        text = json.dumps(
            computed.to_json_dict(),
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
    except (ValueError, OverflowError) as exc:
        raise PpsError(
            f"refusing to write {json_path}: the signal holds a number that is not valid JSON ({exc})"
        ) from exc
    with writing(f"the timing signal {json_path}"):
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path.write_text(text + "\n", encoding="utf-8")
    markdown = render_signal_markdown(document, computed)
    with writing(f"the timing histogram {md_path}"):
        md_path.write_text(markdown, encoding="utf-8")
    return json_path, md_path


def missing_input_lines(computed: ComputedSignal) -> list[str]:
    lines: list[str] = []
    inputs = computed.payload["inputs"]
    if not inputs["appearance_recorded"]:
        lines.append(
            "Revisits: not recorded in this Document; re-parse with the current version to get them."
        )
    text_info = inputs["stills_text"]
    if not text_info["present"] or text_info["covered"] < text_info["of"]:
        lines.append(
            f"Still text: none ({text_info['covered']} of {text_info['of']} Stills); "
            "text-based signals are empty."
        )
    return lines


def render_still_histogram(computed: ComputedSignal) -> str:
    rows = computed.stills
    payload = computed.payload
    max_elapsed = max((row["elapsed_raw"] for row in rows), default=0.0)
    scale = max(1, math.ceil(max_elapsed / BAR_WIDTH)) if rows else 1
    legend = (
        f"Time per Still. Bar = elapsed seconds; '#' = spoken, '.' = silent; "
        f"one character = {scale} s. Notes: boilerplate, pass-through, "
        f"revisited (also N), tangent?, emphasis xN, no text."
    )
    if not payload["inputs"]["appearance_recorded"]:
        legend += " Revisits: not recorded in this Document."
    if not payload["inputs"]["stills_text"]["present"]:
        legend += " Still text: none; tangent? is never shown."
    count = len(rows)
    still_width = max(len("Still"), len(str(count if count else 1)))
    elapsed_width = max(
        len("Elapsed"),
        max((len(f"{row['elapsed_seconds']}s") for row in rows), default=2),
    )
    spoken_width = max(
        len("Spoken"),
        max((len(f"{row['spoken_seconds']}s") for row in rows), default=2),
    )
    header = (
        f"{'Still':>{still_width}}  {'Bar':<{BAR_WIDTH}}  "
        f"{'Elapsed':>{elapsed_width}}  {'Spoken':>{spoken_width}}  Notes"
    )
    lines = [legend, header]
    sidecar_present = payload["inputs"]["stills_text"]["present"]
    id_to_index = {row["still_id"]: row["index"] for row in rows}
    for row in rows:
        bar = _elapsed_bar(row["elapsed_raw"], row["spoken_raw"], scale)
        notes = _still_notes(row, sidecar_present, id_to_index)
        lines.append(
            f"{row['index']:>{still_width}}  {bar:<{BAR_WIDTH}}  "
            f"{row['elapsed_seconds']:>{elapsed_width - 1}}s  "
            f"{row['spoken_seconds']:>{spoken_width - 1}}s"
            + (f"  {notes}" if notes else "")
        )
    return "\n".join(lines)


def render_window_histogram(
    computed: ComputedSignal,
    grades: dict[str, Any] | None = None,
) -> str:
    windows = computed.windows
    thresholds = computed.payload["thresholds"]
    size = thresholds["window_size"]
    stride = thresholds["window_stride"]
    max_spoken = max((row["spoken_raw_total"] for row in windows), default=0.0)
    scale = max(1, math.ceil(max_spoken / BAR_WIDTH)) if windows else 1
    legend = (
        f"Sliding windows of {size} Stills every {stride}. "
        f"Bar = spoken seconds of non-boilerplate Stills; one character = {scale} s. "
        f"z = this window's mean spoken seconds versus all windows, in standard deviations. "
        f"High-signal = revisited, emphasis, or top-quartile explanation density."
    )
    grade_by_id: dict[str, int] = {}
    if grades is not None:
        legend += " Avg grade = mean importance 0-3 from lecture.grades.json."
        for item in grades.get("grades", []):
            if isinstance(item, dict) and "still_id" in item and "importance" in item:
                if isinstance(item["importance"], int) and not isinstance(item["importance"], bool):
                    grade_by_id[item["still_id"]] = item["importance"]
    labels = [row["label"] for row in windows] or ["Window"]
    window_width = max(len("Window"), max(len(label) for label in labels))
    spoken_width = max(
        len("Spoken"),
        max((len(f"{row['spoken_seconds']}s") for row in windows), default=2),
    )
    mean_width = max(
        len("Mean"),
        max((len(f"{row['mean_spoken_seconds']:.1f}s") for row in windows), default=4),
    )
    z_width = max(len("z"), 6)
    peak_width = max(
        len("Peak"),
        max(
            (
                len(str(_index_for(row["peak_still_id"], computed.stills)))
                for row in windows
                if row["peak_still_id"]
            ),
            default=1,
        ),
    )
    header = (
        f"{'Window':<{window_width}}  {'Bar':<{BAR_WIDTH}}  "
        f"{'Spoken':>{spoken_width}}  {'Mean':>{mean_width}}  "
        f"{'z':>{z_width}}  {'Peak':>{peak_width}}  High-signal"
    )
    if grade_by_id:
        header += f"  {'Avg grade':>9}  {'3s':>3}"
    lines = [legend, header]
    index_of = {row["still_id"]: row["index"] for row in computed.stills}
    for row in windows:
        bar = _spoken_bar(row["spoken_raw_total"], scale)
        peak = (
            str(index_of[row["peak_still_id"]])
            if row["peak_still_id"]
            else "-"
        )
        high = ", ".join(str(index_of[sid]) for sid in row["high_signal_still_ids"]) or "-"
        line = (
            f"{row['label']:<{window_width}}  {bar:<{BAR_WIDTH}}  "
            f"{row['spoken_seconds']:>{spoken_width - 1}}s  "
            f"{row['mean_spoken_seconds']:>{mean_width - 1}.1f}s  "
            f"{row['z_score']:>+{z_width}.2f}  {peak:>{peak_width}}  {high}"
        )
        if grade_by_id:
            avg, threes = window_grade_stats(row, grade_by_id)
            line += f"  {avg:>9.1f}  {threes:>3}"
        lines.append(line)
    return "\n".join(lines)


def window_grade_stats(window: dict[str, Any], grade_by_id: dict[str, int]) -> tuple[float, int]:
    scores = [grade_by_id[sid] for sid in window["still_ids"] if sid in grade_by_id]
    if not scores:
        return 0.0, 0
    avg = round(sum(scores) / len(scores), 1)
    threes = sum(1 for score in scores if score == 3)
    return avg, threes


def render_signal_markdown(document: LectureDocument, computed: ComputedSignal) -> str:
    payload = computed.payload
    n_stills = payload["summary"]["still_count"]
    n_windows = payload["summary"]["window_count"]
    lines = [
        f"# {document.title}: timing signal",
        "",
        f"Generated {payload['generated_at']} from lecture.json. "
        f"Duration {format_clock(document.source.duration_seconds)}. "
        f"{n_stills} Stills, {n_windows} windows.",
        "",
    ]
    missing = missing_input_lines(computed)
    if missing:
        lines.extend(missing)
        lines.append("")
    if not document.stills:
        lines.append("No Stills in this Lecture; see transcript.md.")
        lines.append("")
    lines.extend(
        [
            "## Time per Still",
            "",
            "```",
            render_still_histogram(computed),
            "```",
            "",
            "## Sliding windows",
            "",
            "```",
            render_window_histogram(computed),
            "```",
            "",
            "## Per-Still table",
            "",
            "| Still | Appearance | Start | Elapsed | Spoken | Silence | Dead air | Visits | Links | Tokens | Density | Overlap | Emphasis | Notes |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    sidecar_present = payload["inputs"]["stills_text"]["present"]
    id_to_index = {row["still_id"]: row["index"] for row in computed.stills}
    for row in computed.stills:
        notes = _still_notes(row, sidecar_present, id_to_index)
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["index"]),
                    _dash(row["appearance"]),
                    format_clock(row["start_seconds"]),
                    f"{row['elapsed_seconds']}s",
                    f"{row['spoken_seconds']}s",
                    _dash(row["silence_ratio"]),
                    (
                        f"{row['dead_air_count']} ({row['dead_air_seconds']}s)"
                        if row["dead_air_count"]
                        else "0"
                    ),
                    _dash(row["visit_count"]),
                    ", ".join(row["transition_links"] or []) or "-",
                    _dash(row["token_count"]),
                    _dash(row["explanation_density"]),
                    _dash(row["content_overlap"]),
                    str(len(row["emphasis_hits"])) if row["emphasis_hits"] else "-",
                    notes or "-",
                ]
            )
            + " |"
        )
    lines.extend(["", "## Thresholds", "", "| Name | Value |", "| --- | --- |"])
    for name, value in payload["thresholds"].items():
        lines.append(f"| {name} | {value} |")
    lines.append("")
    return "\n".join(lines)


def compare_signal(stored: dict[str, Any], recomputed: dict[str, Any]) -> list[str]:
    diffs: list[str] = []
    skip = {"generated_at"}
    for key in ("schema", "document", "title", "duration_seconds"):
        _compare_field(key, stored.get(key), recomputed.get(key), diffs)
    _compare_mapping("inputs", stored.get("inputs"), recomputed.get("inputs"), diffs)
    _compare_mapping(
        "thresholds", stored.get("thresholds"), recomputed.get("thresholds"), diffs
    )
    stored_stills = {row["still_id"]: row for row in stored.get("stills", []) if "still_id" in row}
    recomputed_stills = {
        row["still_id"]: row for row in recomputed.get("stills", []) if "still_id" in row
    }
    for still_id in stored_stills:
        if still_id not in recomputed_stills:
            diffs.append(f"{still_id}: stored present, recomputed missing")
        else:
            left, right = stored_stills[still_id], recomputed_stills[still_id]
            for field in sorted(set(left) | set(right)):
                if field in skip:
                    continue
                _compare_field(f"{still_id} {field}", left.get(field), right.get(field), diffs)
    for still_id in recomputed_stills:
        if still_id not in stored_stills:
            diffs.append(f"{still_id}: stored missing, recomputed present")
    stored_windows = {row["label"]: row for row in stored.get("windows", []) if "label" in row}
    recomputed_windows = {
        row["label"]: row for row in recomputed.get("windows", []) if "label" in row
    }
    for label in stored_windows:
        if label not in recomputed_windows:
            diffs.append(f"window {label}: stored present, recomputed missing")
        else:
            left, right = stored_windows[label], recomputed_windows[label]
            for field in sorted(set(left) | set(right)):
                _compare_field(
                    f"window {label} {field}", left.get(field), right.get(field), diffs
                )
    for label in recomputed_windows:
        if label not in stored_windows:
            diffs.append(f"window {label}: stored missing, recomputed present")
    _compare_mapping("summary", stored.get("summary"), recomputed.get("summary"), diffs)
    return diffs


def validate_grades(
    document: LectureDocument,
    signal: dict[str, Any],
    grades: dict[str, Any],
) -> list[str]:
    problems: list[str] = []
    if grades.get("schema") != GRADES_SCHEMA:
        problems.append(f"schema must be {GRADES_SCHEMA}")
    raw = grades.get("grades")
    if not isinstance(raw, list):
        problems.append("grades must be a list of objects")
        return problems
    expected = [still.id for still in document.stills]
    seen: list[str] = []
    objects: list[dict[str, Any]] = []
    for position, item in enumerate(raw):
        if not isinstance(item, dict):
            problems.append(f"grades[{position}] must be an object")
            continue
        objects.append(item)
        still_id = item.get("still_id")
        if not isinstance(still_id, str):
            problems.append(f"grades[{position}] still_id must be text")
            continue
        seen.append(still_id)
    expected_set = set(expected)
    seen_set = set(seen)
    for still_id in expected:
        count = seen.count(still_id)
        if count == 0:
            problems.append(f"{still_id} is missing from grades")
        elif count > 1:
            problems.append(f"{still_id} appears more than once")
    for still_id in seen:
        if still_id not in expected_set:
            problems.append(f"{still_id} is not in the Document")
    known_ids = expected_set
    for item in objects:
        still_id = item.get("still_id")
        if not isinstance(still_id, str):
            continue
        prefix = still_id
        importance = item.get("importance")
        if isinstance(importance, bool) or importance not in (0, 1, 2, 3):
            problems.append(f"{prefix} importance must be 0, 1, 2, or 3")
            importance_ok = False
        else:
            importance_ok = True
        category = item.get("category")
        if importance_ok and category != IMPORTANCE_CATEGORY[importance]:
            problems.append(
                f"{prefix} category must be {IMPORTANCE_CATEGORY[importance]}"
            )
        actionable = item.get("actionable_skill")
        if importance_ok:
            if importance <= 1:
                if actionable is not None:
                    problems.append(
                        f"{prefix} actionable_skill must be null when importance <= 1"
                    )
            elif not isinstance(actionable, str) or not actionable.strip():
                problems.append(
                    f"{prefix} actionable_skill must be a non-empty string when importance >= 2"
                )
        fluff = item.get("fluff_filtered")
        if not isinstance(fluff, bool):
            problems.append(f"{prefix} fluff_filtered must be a boolean")
        elif importance_ok and fluff and importance > 1:
            problems.append(f"{prefix} fluff_filtered can be true only when importance <= 1")
        linked = item.get("linked_stills")
        if not isinstance(linked, list):
            problems.append(f"{prefix} linked_stills must be a list")
        else:
            if still_id in linked:
                problems.append(f"{prefix} linked_stills must not include the Still itself")
            if len(linked) != len(set(linked)):
                problems.append(f"{prefix} linked_stills must not contain duplicates")
            for other in linked:
                if other not in known_ids:
                    problems.append(f"{prefix} linked_stills names unknown Still id {other}")
        if not isinstance(item.get("core_topic"), str) or not str(item.get("core_topic")).strip():
            problems.append(f"{prefix} core_topic must be a non-empty string")
        if not isinstance(item.get("justification"), str) or not str(
            item.get("justification")
        ).strip():
            problems.append(f"{prefix} justification must be a non-empty string")
        note = item.get("reconciliation_note")
        if note is not None and not isinstance(note, str):
            problems.append(f"{prefix} reconciliation_note must be a string or null")
    module = grades.get("module")
    tree = grades.get("knowledge_tree")
    if module is not None and not isinstance(module, str):
        problems.append("module must be a string or null")
    if tree is not None and not isinstance(tree, str):
        problems.append("knowledge_tree must be a string or null")
    if (module is None) != (tree is None):
        problems.append("module and knowledge_tree must both be set or both be null")
    _ = signal, seen_set
    return problems


def warn_grades(
    document: LectureDocument,
    signal: dict[str, Any],
    grades: dict[str, Any],
) -> list[str]:
    warnings: list[str] = []
    by_id = {row["still_id"]: row for row in signal.get("stills", [])}
    fluff_limit = signal.get("thresholds", {}).get(
        "fluff_spoken_seconds", FLUFF_SPOKEN_SECONDS
    )
    for item in grades.get("grades", []):
        if not isinstance(item, dict):
            continue
        still_id = item.get("still_id")
        row = by_id.get(still_id, {})
        if item.get("fluff_filtered") is True:
            spoken = row.get("spoken_seconds", 0)
            if isinstance(spoken, (int, float)) and spoken <= fluff_limit:
                warnings.append(
                    f"{still_id} fluff_filtered is true but spoken_seconds is {spoken}"
                )
        if row.get("prescore_zero") and isinstance(item.get("importance"), int):
            if item["importance"] > 0:
                warnings.append(f"{still_id} is prescore_zero but graded {item['importance']}")
    stored_at = grades.get("signal_generated_at")
    current_at = signal.get("generated_at")
    if stored_at is not None and current_at is not None and stored_at != current_at:
        warnings.append("signal_generated_at differs from the stored signal")
    _ = document
    return warnings


def _measure_still(
    still: Still,
    sections: list,
    cues: tuple[Cue, ...],
    stills_text: dict[str, StillText] | None,
    options: SignalThresholds,
) -> dict[str, Any]:
    kept: list[tuple[int, Cue]] = []
    noise_count = 0
    seen_indexes: set[int] = set()
    for section in sections:
        for cue_index in section.cue_indexes:
            if cue_index in seen_indexes or cue_index < 0 or cue_index >= len(cues):
                continue
            seen_indexes.add(cue_index)
            cue = cues[cue_index]
            if cue_is_noise(cue, options.min_words_per_second):
                noise_count += 1
                continue
            kept.append((cue_index, cue))
    kept.sort(key=lambda item: (item[1].start_seconds, item[0]))
    spans: list[tuple[float, float]] = []
    for _index, cue in kept:
        start = max(cue.start_seconds, still.start_seconds)
        end = min(cue.end_seconds, still.end_seconds)
        if end <= start:
            continue
        if not spans or start - spans[-1][1] >= options.pause_seconds:
            spans.append((start, end))
        else:
            spans[-1] = (spans[-1][0], max(spans[-1][1], end))
    elapsed_raw = still.end_seconds - still.start_seconds
    spoken_raw = sum(end - start for start, end in spans)
    elapsed_seconds = round_half_up(elapsed_raw)
    spoken_seconds = round_half_up(spoken_raw)
    silence_ratio = round(
        max(0.0, elapsed_raw - spoken_raw) / max(elapsed_raw, 1.0), 2
    )
    dead_gaps: list[float] = []
    if not spans:
        dead_gaps.append(elapsed_raw)
    else:
        dead_gaps.append(spans[0][0] - still.start_seconds)
        for previous, current in zip(spans, spans[1:]):
            dead_gaps.append(current[0] - previous[1])
        dead_gaps.append(still.end_seconds - spans[-1][1])
    dead_air = [gap for gap in dead_gaps if gap >= options.dead_air_seconds]
    said = " ".join(section.said for section in sections if section.said).strip()
    text_entry = stills_text.get(still.id) if stills_text is not None else None
    pass_through = elapsed_raw < options.pass_through_seconds
    admin_title = bool(text_entry and ADMIN_TITLE.search(text_entry.title))
    boilerplate = (
        pass_through
        or spoken_raw < options.boilerplate_spoken_seconds
        or admin_title
    )
    prescore_zero = boilerplate and spoken_raw < options.prescore_zero_spoken_seconds
    title = has_diagram = token_count = density = overlap = tangent = None
    if text_entry is not None:
        title = text_entry.title
        has_diagram = text_entry.has_diagram
        still_tokens = tokenize(
            f"{text_entry.title} {text_entry.text}", min_chars=options.min_token_chars
        )
        token_count = len(still_tokens)
        transcript_set = set(tokenize(said, min_chars=options.min_token_chars))
        density = round(spoken_raw / max(token_count, 1), 2)
        unique_still = set(still_tokens)
        overlap = round(len(unique_still & transcript_set) / max(len(unique_still), 1), 2)
        tangent = (
            spoken_raw > options.tangent_spoken_seconds
            and overlap < options.tangent_overlap
            and not has_diagram
        )
    emphasis_hits = []
    for cue_index, cue in kept:
        for phrase, pattern in _EMPHASIS_PATTERNS:
            if pattern.search(cue.text):
                emphasis_hits.append(
                    {
                        "phrase": phrase,
                        "at_seconds": cue.start_seconds,
                        "cue_index": cue_index,
                    }
                )
    return {
        "still_id": still.id,
        "index": still.index,
        "appearance": still.appearance if still.appearance is not None else None,
        "start_seconds": still.start_seconds,
        "end_seconds": still.end_seconds,
        "elapsed_seconds": elapsed_seconds,
        "spoken_seconds": spoken_seconds,
        "silence_ratio": silence_ratio,
        "dead_air_count": len(dead_air),
        "dead_air_seconds": round_half_up(sum(dead_air)) if dead_air else 0,
        "cue_count": len(kept),
        "noise_cue_count": noise_count,
        "word_count": sum(cue_word_count(cue) for _index, cue in kept),
        "pass_through": pass_through,
        "boilerplate": boilerplate,
        "prescore_zero": prescore_zero,
        "title": title,
        "has_diagram": has_diagram,
        "token_count": token_count,
        "explanation_density": density,
        "content_overlap": overlap,
        "suspect_tangent": tangent,
        "emphasis_hits": emphasis_hits,
        "said_words_excerpt": _excerpt(said),
        "elapsed_raw": elapsed_raw,
        "spoken_raw": spoken_raw,
    }


def _visit_fields(
    stills: tuple[Still, ...],
    rows: list[dict[str, Any]],
    recorded: bool,
) -> dict[str, dict[str, Any]]:
    empty = {
        "appearance": None,
        "visit_count": None,
        "revisited": None,
        "same_appearance": None,
        "transition_links": None,
    }
    if not recorded:
        return {still.id: dict(empty) for still in stills}
    pass_through = {row["still_id"]: row["pass_through"] for row in rows}
    groups: dict[int, list[Still]] = {}
    for still in stills:
        assert still.appearance is not None
        groups.setdefault(still.appearance, []).append(still)
    visible = [still for still in stills if not pass_through[still.id]]
    visits: dict[int, list[list[Still]]] = {}
    run: list[Still] = []
    for still in visible:
        if run and run[-1].appearance == still.appearance:
            run.append(still)
        else:
            if run:
                visits.setdefault(run[0].appearance or 0, []).append(run)
            run = [still]
    if run:
        visits.setdefault(run[0].appearance or 0, []).append(run)
    visible_ids = [still.id for still in visible]
    result: dict[str, dict[str, Any]] = {}
    for still in stills:
        mates = groups.get(still.appearance or 0, [still])
        same = [mate.id for mate in mates if mate.id != still.id]
        if pass_through[still.id]:
            result[still.id] = {
                "appearance": still.appearance,
                "visit_count": 0,
                "revisited": False,
                "same_appearance": same,
                "transition_links": [],
            }
            continue
        group_visits = visits.get(still.appearance or 0, [])
        links: set[Still] = set()
        for visit in group_visits[1:]:
            first_at = visible_ids.index(visit[0].id)
            last_at = visible_ids.index(visit[-1].id)
            if first_at > 0:
                before = visible[first_at - 1]
                if before.appearance != still.appearance:
                    links.add(before)
            if last_at + 1 < len(visible):
                after = visible[last_at + 1]
                if after.appearance != still.appearance:
                    links.add(after)
        result[still.id] = {
            "appearance": still.appearance,
            "visit_count": len(group_visits),
            "revisited": len(group_visits) > 1,
            "same_appearance": same,
            "transition_links": [item.id for item in sorted(links, key=lambda item: item.index)],
        }
    return result


def _measure_windows(
    still_rows: list[dict[str, Any]],
    options: SignalThresholds,
) -> list[dict[str, Any]]:
    count = len(still_rows)
    densities = [
        row["explanation_density"]
        for row in still_rows
        if not row["boilerplate"] and row["explanation_density"] is not None
    ]
    cutoff = _nearest_rank(densities, options.high_density_quantile)
    bounds = window_bounds(count, options.window_size, options.window_stride)
    windows: list[dict[str, Any]] = []
    for first, last in bounds:
        members = still_rows[first - 1 : last]
        contributing = [row for row in members if not row["boilerplate"]]
        spoken_raw_total = sum(row["spoken_raw"] for row in contributing)
        mean_raw = spoken_raw_total / len(contributing) if contributing else 0.0
        peak = None
        if contributing:
            best = contributing[0]
            for row in contributing[1:]:
                if row["spoken_raw"] > best["spoken_raw"] or (
                    row["spoken_raw"] == best["spoken_raw"] and row["index"] < best["index"]
                ):
                    best = row
            peak = best["still_id"]
        high: list[str] = []
        for row in members:
            revisited = row["revisited"] is True
            emphasized = bool(row["emphasis_hits"])
            dense = (
                row["explanation_density"] is not None
                and cutoff is not None
                and row["explanation_density"] >= cutoff
            )
            if revisited or emphasized or dense:
                high.append(row["still_id"])
        windows.append(
            {
                "label": f"{first}-{last}",
                "first_index": first,
                "last_index": last,
                "still_ids": [row["still_id"] for row in members],
                "contributing_still_ids": [row["still_id"] for row in contributing],
                "spoken_seconds": round_half_up(spoken_raw_total),
                "mean_spoken_seconds": round(mean_raw, 1),
                "z_score": 0.0,
                "peak_still_id": peak,
                "high_signal_still_ids": high,
                "spoken_raw_total": spoken_raw_total,
                "mean_raw": mean_raw,
            }
        )
    means = [row["mean_raw"] for row in windows]
    if len(windows) >= 2:
        sigma = statistics.pstdev(means)
        mu = statistics.mean(means)
        if sigma > 0:
            for row in windows:
                row["z_score"] = round((row["mean_raw"] - mu) / sigma, 2)
    return windows


def _summary(
    document: LectureDocument,
    still_rows: list[dict[str, Any]],
    windows: list[dict[str, Any]],
    appearance_recorded: bool,
) -> dict[str, Any]:
    densities = [
        row["explanation_density"]
        for row in still_rows
        if not row["boilerplate"] and row["explanation_density"] is not None
    ]
    revisited_appearances: set[int] = set()
    if appearance_recorded:
        for row in still_rows:
            if row["revisited"] is True and row["appearance"] is not None:
                revisited_appearances.add(row["appearance"])
    return {
        "still_count": len(document.stills),
        "elapsed_seconds": round_half_up(sum(row["elapsed_raw"] for row in still_rows)),
        "spoken_seconds": round_half_up(sum(row["spoken_raw"] for row in still_rows)),
        "boilerplate_count": sum(1 for row in still_rows if row["boilerplate"]),
        "pass_through_count": sum(1 for row in still_rows if row["pass_through"]),
        "revisited_appearance_count": (
            len(revisited_appearances) if appearance_recorded else None
        ),
        "tangent_count": sum(1 for row in still_rows if row["suspect_tangent"] is True),
        "emphasis_hit_count": sum(len(row["emphasis_hits"]) for row in still_rows),
        "window_count": len(windows),
        "high_density_cutoff": _nearest_rank(densities, HIGH_DENSITY_QUANTILE),
    }


def _nearest_rank(values: list[float], quantile: float) -> float | None:
    if len(values) < 4:
        return None
    ordered = sorted(values)
    position = math.ceil(quantile * len(ordered))
    return ordered[position - 1]


def _elapsed_bar(elapsed_raw: float, spoken_raw: float, scale: int) -> str:
    if elapsed_raw <= 0:
        return ""
    length = max(1, round_half_up(elapsed_raw / scale))
    spoken_chars = min(length, round_half_up(spoken_raw / scale))
    return "#" * spoken_chars + "." * (length - spoken_chars)


def _spoken_bar(spoken_raw_total: float, scale: int) -> str:
    if spoken_raw_total <= 0:
        return ""
    length = max(1, round_half_up(spoken_raw_total / scale))
    return "#" * length


def _still_notes(
    row: dict[str, Any],
    sidecar_present: bool,
    id_to_index: dict[str, int],
) -> str:
    parts: list[str] = []
    if row["pass_through"]:
        parts.append("pass-through")
    if row["boilerplate"]:
        parts.append("boilerplate")
    if row["revisited"] is True:
        others = [
            str(id_to_index[sid])
            for sid in row["same_appearance"] or []
            if sid in id_to_index
        ]
        if others:
            parts.append(f"revisited (also {', '.join(others)})")
        else:
            parts.append("revisited")
    if row["suspect_tangent"] is True:
        parts.append("tangent?")
    hits = row["emphasis_hits"] or []
    if hits:
        parts.append(f"emphasis x{len(hits)}")
    if sidecar_present and row["token_count"] is None:
        parts.append("no text")
    return ", ".join(parts)


def _excerpt(said: str) -> str:
    text = " ".join(said.split()[:EXCERPT_WORDS])
    return text[:EXCERPT_CHARS]


def _dash(value: Any) -> str:
    return "-" if value is None else str(value)


def _without_keys(row: dict[str, Any], keys: Iterable[str]) -> dict[str, Any]:
    skip = set(keys)
    return {key: value for key, value in row.items() if key not in skip}


def _index_for(still_id: str | None, rows: list[dict[str, Any]]) -> int:
    if still_id is None:
        return 0
    for row in rows:
        if row["still_id"] == still_id:
            return row["index"]
    return 0


def _compare_mapping(
    prefix: str, stored: Any, recomputed: Any, diffs: list[str]
) -> None:
    if not isinstance(stored, dict) or not isinstance(recomputed, dict):
        _compare_field(prefix, stored, recomputed, diffs)
        return
    for key in sorted(set(stored) | set(recomputed)):
        left, right = stored.get(key), recomputed.get(key)
        if isinstance(left, dict) or isinstance(right, dict):
            _compare_mapping(f"{prefix} {key}", left, right, diffs)
        else:
            _compare_field(f"{prefix} {key}", left, right, diffs)


def _compare_field(path: str, stored: Any, recomputed: Any, diffs: list[str]) -> None:
    if stored != recomputed:
        diffs.append(f"{path}: stored {_fmt(stored)}, recomputed {_fmt(recomputed)}")


def _fmt(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)
