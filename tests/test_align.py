from __future__ import annotations

import unittest

from podleparsesskewl.align import align_cues_to_stills
from podleparsesskewl.document import Cue, Still


def _still(index: int, start: float, end: float) -> Still:
    return Still(
        id=f"still-{index:03d}",
        index=index,
        start_seconds=start,
        end_seconds=end,
        image=f"stills/still-{index:03d}.png",
    )


class AlignTests(unittest.TestCase):
    def test_cues_follow_the_still_that_contains_their_midpoint(self) -> None:
        stills = [_still(1, 0.0, 5.0), _still(2, 5.0, 10.0)]
        cues = [
            Cue(0.0, 2.0, "On the first shown."),
            Cue(4.0, 6.0, "Straddles the cut, midpoint 5.0 belongs to still 2."),
            Cue(7.0, 8.0, "On the second shown."),
        ]
        sections = align_cues_to_stills(cues, stills)
        self.assertEqual(len(sections), 2)
        self.assertEqual(sections[0].still_id, "still-001")
        self.assertEqual(sections[0].said, "On the first shown.")
        self.assertEqual(sections[0].cue_indexes, (0,))
        self.assertEqual(sections[1].still_id, "still-002")
        self.assertIn("Straddles the cut", sections[1].said)
        self.assertIn("On the second shown.", sections[1].said)
        self.assertEqual(sections[1].cue_indexes, (1, 2))

    def test_last_still_includes_a_cue_at_exactly_the_end(self) -> None:
        stills = [_still(1, 0.0, 4.0), _still(2, 4.0, 8.0)]
        cues = [Cue(8.0, 8.0, "Last word.")]
        sections = align_cues_to_stills(cues, stills)
        self.assertEqual(sections[0].said, "")
        self.assertEqual(sections[1].said, "Last word.")

    def test_empty_cues_still_emit_one_section_per_still(self) -> None:
        stills = [_still(1, 0.0, 3.0)]
        sections = align_cues_to_stills([], stills)
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].said, "")
        self.assertEqual(sections[0].cue_indexes, ())
