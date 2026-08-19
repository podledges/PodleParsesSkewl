"""Align Said (transcript cues) with Shown (Still intervals)."""

from __future__ import annotations

from podleparsesskewl.document import Cue, Section, Still


def align_cues_to_stills(
    cues: tuple[Cue, ...] | list[Cue],
    stills: list[Still] | tuple[Still, ...],
) -> list[Section]:
    """Assign each cue to the Still whose interval contains the cue midpoint.

    Segment grain is speech-during-still: one Section per Still, containing
    every cue whose midpoint falls in that Still.
    """
    bounds = [(item.id, item.start_seconds, item.end_seconds) for item in stills]
    buckets: list[list[tuple[int, Cue]]] = [[] for _ in bounds]
    last_index = len(bounds) - 1
    for cue_index, cue in enumerate(cues):
        if not cue.text.strip():
            continue
        midpoint = (cue.start_seconds + cue.end_seconds) / 2.0
        assigned = False
        for still_index, (still_id, start, end) in enumerate(bounds):
            if _contains(midpoint, start, end, is_last=(still_index == last_index)):
                buckets[still_index].append((cue_index, cue))
                assigned = True
                break
        if not assigned and bounds:
            _last_id, last_start, last_end = bounds[-1]
            if midpoint >= last_start or last_end == last_start:
                buckets[-1].append((cue_index, cue))
    sections: list[Section] = []
    for still_index, (still_id, _start, _end) in enumerate(bounds):
        owned = buckets[still_index]
        said = " ".join(cue.text.strip() for _index, cue in owned if cue.text.strip())
        sections.append(
            Section(
                still_id=still_id,
                said=said,
                cue_indexes=tuple(index for index, _cue in owned),
            )
        )
    return sections


def _contains(point: float, start: float, end: float, *, is_last: bool) -> bool:
    if is_last:
        return start <= point <= end
    return start <= point < end
