"""Segment a Recording into Stills from sampled frame signatures."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_SAMPLE_WIDTH = 160
DEFAULT_SAMPLE_HEIGHT = 90
DEFAULT_BLOCK = 16
DEFAULT_BLOCK_THRESHOLD = 0.12
DEFAULT_CHANGE_RATIO = 0.15
DEFAULT_MIN_HOLD_SECONDS = 1.5
DEFAULT_SAMPLE_FPS = 1.0


@dataclass(frozen=True)
class FrameSignature:
    """A compact grayscale sample of one decoded frame."""

    time_seconds: float
    width: int
    height: int
    samples: bytes


@dataclass(frozen=True)
class StillInterval:
    """A stable visual interval before images are extracted."""

    start_seconds: float
    end_seconds: float
    representative_seconds: float


def block_change_ratio(
    first: bytes,
    second: bytes,
    width: int,
    height: int,
    *,
    block: int = DEFAULT_BLOCK,
    block_threshold: float = DEFAULT_BLOCK_THRESHOLD,
) -> float:
    """Share of blocks whose mean absolute difference exceeds `block_threshold`.

    A small webcam bubble only moves a few blocks. A slide change moves many.
    """
    if not first or len(first) != len(second) or width <= 0 or height <= 0:
        return 1.0
    if len(first) != width * height:
        return 1.0
    changed = 0
    total = 0
    for top in range(0, height, block):
        block_h = min(block, height - top)
        for left in range(0, width, block):
            block_w = min(block, width - left)
            total += 1
            diff = 0
            count = block_w * block_h
            for row in range(block_h):
                offset = (top + row) * width + left
                for col in range(block_w):
                    index = offset + col
                    diff += abs(first[index] - second[index])
            if (diff / (count * 255.0)) >= block_threshold:
                changed += 1
    if total == 0:
        return 1.0
    return changed / total


def segment_stills(
    frames: list[FrameSignature],
    *,
    duration_seconds: float,
    change_ratio: float = DEFAULT_CHANGE_RATIO,
    min_hold_seconds: float = DEFAULT_MIN_HOLD_SECONDS,
    block: int = DEFAULT_BLOCK,
    block_threshold: float = DEFAULT_BLOCK_THRESHOLD,
) -> list[StillInterval]:
    """Group sampled frames into Still intervals.

    A new Still starts only when enough blocks change *and* the new look
    holds for `min_hold_seconds`. That keeps flicker and webcam bubbles
    from splitting a stable slide.
    """
    if duration_seconds < 0:
        duration_seconds = 0.0
    if not frames:
        return [
            StillInterval(
                start_seconds=0.0,
                end_seconds=duration_seconds,
                representative_seconds=0.0,
            )
        ]

    current_start = max(0.0, frames[0].time_seconds)
    current_samples = frames[0].samples
    current_rep = frames[0].time_seconds
    width = frames[0].width
    height = frames[0].height
    starts: list[tuple[float, float]] = []

    index = 1
    while index < len(frames):
        frame = frames[index]
        ratio = block_change_ratio(
            current_samples,
            frame.samples,
            width,
            height,
            block=block,
            block_threshold=block_threshold,
        )
        if ratio >= change_ratio:
            hold_until = frame.time_seconds + min_hold_seconds
            new_samples = frame.samples
            hold_index = index
            stable = True
            while hold_index < len(frames) and frames[hold_index].time_seconds < hold_until:
                hold_ratio = block_change_ratio(
                    new_samples,
                    frames[hold_index].samples,
                    width,
                    height,
                    block=block,
                    block_threshold=block_threshold,
                )
                if hold_ratio >= change_ratio:
                    stable = False
                    break
                hold_index += 1
            if stable:
                starts.append((current_start, current_rep))
                current_start = frame.time_seconds
                current_samples = new_samples
                current_rep = frame.time_seconds
                index = max(hold_index, index + 1)
                continue
        index += 1

    starts.append((current_start, current_rep))
    intervals: list[StillInterval] = []
    for position, (start, rep) in enumerate(starts):
        if position + 1 < len(starts):
            end = starts[position + 1][0]
        else:
            end = duration_seconds
        if end < start:
            end = start
        intervals.append(
            StillInterval(
                start_seconds=start,
                end_seconds=end,
                representative_seconds=min(max(rep, start), end),
            )
        )
    if intervals and intervals[-1].end_seconds < duration_seconds:
        last = intervals[-1]
        intervals[-1] = StillInterval(
            start_seconds=last.start_seconds,
            end_seconds=duration_seconds,
            representative_seconds=last.representative_seconds,
        )
    return intervals
