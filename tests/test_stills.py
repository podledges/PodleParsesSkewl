from __future__ import annotations

import random
import unittest

from podleparsesskewl.stills import FrameSignature, segment_stills

WIDTH = 160
HEIGHT = 90
SLIDE_COLUMNS = 128
PAPER = 235
INK = 30


def _frame(time: float, slide: int, webcam: int) -> FrameSignature:
    rows = []
    for _row in range(HEIGHT):
        left = bytes([slide]) * SLIDE_COLUMNS
        right = bytes([webcam]) * (WIDTH - SLIDE_COLUMNS)
        rows.append(left + right)
    return FrameSignature(
        time_seconds=time,
        width=WIDTH,
        height=HEIGHT,
        samples=b"".join(rows),
    )


class StillSegmentationTests(unittest.TestCase):
    def test_no_frames_yields_one_still_for_the_duration(self) -> None:
        intervals = segment_stills([], duration_seconds=12.0)
        self.assertEqual(len(intervals), 1)
        self.assertEqual(intervals[0].start_seconds, 0.0)
        self.assertEqual(intervals[0].end_seconds, 12.0)

    def test_unchanged_frames_are_one_still(self) -> None:
        frames = [_frame(float(i), slide=40, webcam=40) for i in range(8)]
        intervals = segment_stills(frames, duration_seconds=8.0)
        self.assertEqual(len(intervals), 1)
        self.assertEqual(intervals[0].start_seconds, 0.0)
        self.assertEqual(intervals[0].end_seconds, 8.0)

    def test_full_frame_slide_change_splits_stills(self) -> None:
        frames = [_frame(float(i), slide=20, webcam=20) for i in range(5)]
        frames += [_frame(float(i), slide=200, webcam=200) for i in range(5, 10)]
        intervals = segment_stills(frames, duration_seconds=10.0, min_hold_seconds=1.5)
        self.assertEqual(len(intervals), 2)
        self.assertEqual(intervals[0].start_seconds, 0.0)
        self.assertEqual(intervals[0].end_seconds, 5.0)
        self.assertEqual(intervals[1].start_seconds, 5.0)
        self.assertEqual(intervals[1].end_seconds, 10.0)
        self.assertEqual(intervals[1].representative_seconds, 5.0)

    def test_webcam_bubble_flicker_does_not_split_a_stable_slide(self) -> None:
        slide = _white_slide(seed=1, bullets=4)
        frames = [_with_bubble(slide, t) for t in range(12)]
        intervals = segment_stills(frames, duration_seconds=12.0)
        self.assertEqual(len(intervals), 1)
        self.assertEqual(intervals[0].start_seconds, 0.0)
        self.assertEqual(intervals[0].end_seconds, 12.0)

    def test_change_that_does_not_hold_is_ignored(self) -> None:
        frames = [_frame(float(i), slide=20, webcam=20) for i in range(4)]
        frames.append(_frame(4.0, slide=200, webcam=200))
        frames += [_frame(float(i), slide=20, webcam=20) for i in range(5, 8)]
        intervals = segment_stills(frames, duration_seconds=8.0, min_hold_seconds=1.5)
        self.assertEqual(len(intervals), 1)
        self.assertEqual(intervals[0].end_seconds, 8.0)

    def test_last_second_flicker_does_not_become_a_still(self) -> None:
        frames = [_frame(float(i), slide=20, webcam=20) for i in range(5)]
        frames.append(_frame(5.0, slide=200, webcam=200))
        intervals = segment_stills(frames, duration_seconds=6.0, min_hold_seconds=1.5)
        self.assertEqual(len(intervals), 1)
        self.assertEqual(intervals[0].end_seconds, 6.0)

    def test_text_heavy_full_slide_swap_splits_at_defaults(self) -> None:
        first = _white_slide(seed=1, bullets=4)
        second = _white_slide(seed=2, bullets=4)
        frames = [_with_bubble(first, t) for t in range(8)]
        frames += [_with_bubble(second, t) for t in range(8, 16)]
        intervals = segment_stills(frames, duration_seconds=16.0)
        self.assertEqual(len(intervals), 2)
        self.assertEqual(intervals[0].end_seconds, 8.0)
        self.assertEqual(intervals[1].start_seconds, 8.0)

    def test_one_bullet_progressive_build_stays_merged_at_defaults(self) -> None:
        title_only = _white_slide(seed=1, bullets=0)
        one_bullet = _white_slide(seed=1, bullets=1)
        frames = [_with_bubble(title_only, t) for t in range(5)]
        frames += [_with_bubble(one_bullet, t) for t in range(5, 10)]
        intervals = segment_stills(frames, duration_seconds=10.0)
        self.assertEqual(len(intervals), 1)


def _white_slide(seed: int, bullets: int) -> bytearray:
    pixels = bytearray([PAPER]) * (WIDTH * HEIGHT)
    band = 60 + seed * 10
    for row in range(0, 15):
        for col in range(WIDTH):
            pixels[row * WIDTH + col] = band
    for n in range(bullets):
        text_row = 26 + n * 11
        line_rng = random.Random(seed * 10 + n)
        for row in (text_row, text_row + 1, text_row + 2):
            for col in range(12, 140):
                if line_rng.random() < 0.45:
                    pixels[row * WIDTH + col] = INK
    return pixels


def _with_bubble(base: bytearray, tick: int) -> FrameSignature:
    rng = random.Random(1000 + tick)
    frame = bytearray(base)
    for row in range(66, 88):
        for col in range(134, 158):
            frame[row * WIDTH + col] = rng.randrange(256)
    return FrameSignature(
        time_seconds=float(tick),
        width=WIDTH,
        height=HEIGHT,
        samples=bytes(frame),
    )
