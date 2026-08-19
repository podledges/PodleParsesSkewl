from __future__ import annotations

import unittest

from podleparsesskewl.stills import FrameSignature, segment_stills

WIDTH = 160
HEIGHT = 90
SLIDE_COLUMNS = 128


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
        frames = []
        for i in range(10):
            frames.append(_frame(float(i), slide=30, webcam=0 if i % 2 == 0 else 255))
        for i in range(10, 20):
            frames.append(_frame(float(i), slide=220, webcam=0 if i % 2 == 0 else 255))
        intervals = segment_stills(frames, duration_seconds=20.0, min_hold_seconds=1.5)
        self.assertEqual(len(intervals), 2)
        self.assertEqual(intervals[0].end_seconds, 10.0)
        self.assertEqual(intervals[1].start_seconds, 10.0)

    def test_change_that_does_not_hold_is_ignored(self) -> None:
        frames = [_frame(float(i), slide=20, webcam=20) for i in range(4)]
        frames.append(_frame(4.0, slide=200, webcam=200))
        frames += [_frame(float(i), slide=20, webcam=20) for i in range(5, 8)]
        intervals = segment_stills(frames, duration_seconds=8.0, min_hold_seconds=1.5)
        self.assertEqual(len(intervals), 1)
        self.assertEqual(intervals[0].end_seconds, 8.0)
