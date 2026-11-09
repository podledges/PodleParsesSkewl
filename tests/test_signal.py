from __future__ import annotations

import contextlib
import io
import json
import statistics
import tempfile
import unittest
from pathlib import Path

from podleparsesskewl.align import align_cues_to_stills
from podleparsesskewl.cli import main
from podleparsesskewl.document import Cue, LectureDocument, SourceInfo, Still, Transcript
from podleparsesskewl.errors import PpsError
from podleparsesskewl.pipeline import write_document
from podleparsesskewl.signal import (
    BRIEF_NAME,
    GRADES_JSON,
    GRADES_SCHEMA,
    SIGNAL_JSON,
    SIGNAL_MD,
    SIGNAL_SCHEMA,
    STILLS_TEXT_NAME,
    STILLS_TEXT_SCHEMA,
    TAUGHT_NAME,
    StillText,
    compare_signal,
    compute_signal,
    cue_is_noise,
    load_stills_text,
    render_signal_markdown,
    render_still_histogram,
    render_window_histogram,
    round_half_up,
    tokenize,
    validate_grades,
    warn_grades,
    window_bounds,
    write_signal_views,
)


def _document(
    stills: list[tuple] | None = None,
    cues: list[tuple] | None = None,
    *,
    title: str = "Test lecture",
) -> LectureDocument:
    if stills is None:
        stills = [(0.0, 10.0, 1)]
    if cues is None:
        cues = [(1.0, 4.0, "hello class this is speech")]
    still_objs = []
    for index, item in enumerate(stills, start=1):
        start, end, *rest = item
        appearance = rest[0] if rest else None
        still_objs.append(
            Still(
                f"still-{index:03d}",
                index,
                float(start),
                float(end),
                f"stills/still-{index:03d}.png",
                appearance,
            )
        )
    cue_objs = tuple(Cue(float(start), float(end), text) for start, end, text in cues)
    sections = tuple(align_cues_to_stills(cue_objs, still_objs))
    duration = max((still.end_seconds for still in still_objs), default=0.0)
    if cue_objs:
        duration = max(duration, max(cue.end_seconds for cue in cue_objs))
    return LectureDocument(
        title=title,
        source=SourceInfo("lecture.mp4", duration, "sidecar:srt:lecture.srt"),
        stills=tuple(still_objs),
        transcript=Transcript(cue_objs, "sidecar:srt:lecture.srt"),
        sections=sections,
    )


def _row(computed, still_id: str) -> dict:
    for row in computed.stills:
        if row["still_id"] == still_id:
            return row
    raise AssertionError(still_id)


def _valid_grades(document: LectureDocument, computed, **overrides) -> dict:
    grades = []
    for still in document.stills:
        row = _row(computed, still.id)
        importance = 0 if row["prescore_zero"] or row["boilerplate"] else 2
        if importance <= 1:
            category = "noise_admin_or_tangent" if importance == 0 else "low_yield_context"
            skill = None
        else:
            category = "core_testable_concept"
            skill = f"Explain {still.id}"
        grades.append(
            {
                "still_id": still.id,
                "importance": importance,
                "category": category,
                "fluff_filtered": False,
                "core_topic": f"topic {still.id}",
                "actionable_skill": skill,
                "linked_stills": [],
                "justification": f"{row['elapsed_seconds']} s elapsed",
                "reconciliation_note": None,
            }
        )
    payload = {
        "schema": GRADES_SCHEMA,
        "document": "lecture.json",
        "signal_generated_at": computed.payload["generated_at"],
        "graded_by": "agent: test",
        "module": None,
        "knowledge_tree": None,
        "grades": grades,
    }
    payload.update(overrides)
    return payload


class RoundingTests(unittest.TestCase):
    def test_half_up(self) -> None:
        self.assertEqual(round_half_up(2.5), 3)
        self.assertEqual(round_half_up(2.49), 2)
        self.assertEqual(round_half_up(0), 0)


class NoiseFilterTests(unittest.TestCase):
    def test_empty_and_tags_are_noise(self) -> None:
        self.assertTrue(cue_is_noise(Cue(0, 1, "")))
        self.assertTrue(cue_is_noise(Cue(0, 1, "   ")))
        self.assertTrue(cue_is_noise(Cue(0, 1, "[music]")))
        self.assertTrue(cue_is_noise(Cue(0, 1, "(upbeat music)")))
        self.assertTrue(cue_is_noise(Cue(0, 1, "♪♪")))
        self.assertTrue(cue_is_noise(Cue(0, 1, "[BLANK_AUDIO]")))

    def test_words_per_second_threshold(self) -> None:
        four = Cue(0.0, 10.0, "one two three four")
        five = Cue(0.0, 10.0, "one two three four five")
        self.assertTrue(cue_is_noise(four))
        self.assertFalse(cue_is_noise(five))

    def test_zero_duration_cue_with_words_is_kept(self) -> None:
        cue = Cue(5.0, 5.0, "hello world")
        self.assertFalse(cue_is_noise(cue))
        document = _document([(0.0, 10.0, 1)], [(5.0, 5.0, "hello world")])
        row = _row(compute_signal(document), "still-001")
        self.assertEqual(row["spoken_seconds"], 0)
        self.assertEqual(row["cue_count"], 1)
        self.assertGreater(row["word_count"], 0)


class SpanTests(unittest.TestCase):
    def test_pause_boundary_merges_and_splits(self) -> None:
        merged = _document([(0.0, 20.0, 1)], [(0.0, 5.0, "aaaa bbbb cccc"), (6.49, 10.0, "dddd eeee ffff")])
        split = _document([(0.0, 20.0, 1)], [(0.0, 5.0, "aaaa bbbb cccc"), (6.5, 10.0, "dddd eeee ffff")])
        self.assertEqual(_row(compute_signal(merged), "still-001")["spoken_seconds"], 10)
        self.assertEqual(_row(compute_signal(split), "still-001")["spoken_seconds"], 9)

    def test_straddling_cue_is_clipped_to_the_still(self) -> None:
        document = _document([(0.0, 10.0, 1)], [(8.0, 12.0, "clipped speech across the edge")])
        row = _row(compute_signal(document), "still-001")
        self.assertLessEqual(row["spoken_seconds"], row["elapsed_seconds"])
        self.assertEqual(row["spoken_seconds"], 2)

    def test_cue_outside_the_still_contributes_zero_seconds(self) -> None:
        document = _document([(0.0, 10.0, 1)], [(20.0, 25.0, "this speech belongs elsewhere really")])
        # Midpoint 22.5 is outside still-001; align will not assign it. Force a Section.
        from podleparsesskewl.document import Section

        forced = LectureDocument(
            title=document.title,
            source=document.source,
            stills=document.stills,
            transcript=document.transcript,
            sections=(Section("still-001", document.transcript.cues[0].text, (0,)),),
        )
        row = _row(compute_signal(forced), "still-001")
        self.assertEqual(row["spoken_seconds"], 0)
        self.assertEqual(row["cue_count"], 1)


class DeadAirTests(unittest.TestCase):
    def test_dead_air_threshold(self) -> None:
        under = _document([(0.0, 10.0, 1)], [(0.0, 4.0, "talk talk talk"), (5.99, 8.0, "more talk here")])
        over = _document([(0.0, 10.0, 1)], [(0.0, 4.0, "talk talk talk"), (6.0, 8.0, "more talk here")])
        self.assertEqual(_row(compute_signal(under), "still-001")["dead_air_count"], 1)
        self.assertEqual(_row(compute_signal(over), "still-001")["dead_air_count"], 2)

    def test_silent_still_is_one_pause_and_full_silence(self) -> None:
        document = _document([(0.0, 10.0, 1)], [])
        row = _row(compute_signal(document), "still-001")
        self.assertEqual(row["dead_air_count"], 1)
        self.assertEqual(row["dead_air_seconds"], 10)
        self.assertEqual(row["silence_ratio"], 1.0)

    def test_wall_to_wall_speech_has_zero_silence(self) -> None:
        document = _document([(0.0, 10.0, 1)], [(0.0, 10.0, "talk " * 8)])
        row = _row(compute_signal(document), "still-001")
        self.assertEqual(row["silence_ratio"], 0.0)
        self.assertEqual(row["dead_air_count"], 0)


class FlagTests(unittest.TestCase):
    def test_pass_through_boundary(self) -> None:
        under = _row(compute_signal(_document([(0.0, 2.99, 1)], [])), "still-001")
        edge = _row(compute_signal(_document([(0.0, 3.0, 1)], [])), "still-001")
        self.assertTrue(under["pass_through"])
        self.assertFalse(edge["pass_through"])

    def test_boilerplate_spoken_boundary_and_title(self) -> None:
        short = _document([(0.0, 20.0, 1)], [(0.0, 2.99, "aa bb cc dd ee")])
        edge = _document([(0.0, 20.0, 1)], [(0.0, 3.0, "aa bb cc dd ee")])
        self.assertTrue(_row(compute_signal(short), "still-001")["boilerplate"])
        self.assertFalse(_row(compute_signal(edge), "still-001")["boilerplate"])
        agenda = compute_signal(
            _document([(0.0, 20.0, 1)], [(0.0, 10.0, "talk " * 8)]),
            {"still-001": StillText("Agenda", "items", False)},
        )
        agent = compute_signal(
            _document([(0.0, 20.0, 1)], [(0.0, 10.0, "talk " * 8)]),
            {"still-001": StillText("Agent-based models", "items", False)},
        )
        self.assertTrue(_row(agenda, "still-001")["boilerplate"])
        self.assertFalse(_row(agent, "still-001")["boilerplate"])

    def test_prescore_zero_boundary(self) -> None:
        under = compute_signal(
            _document([(0.0, 20.0, 1)], [(0.0, 4.99, "talk " * 8)]),
            {"still-001": StillText("Agenda", "", False)},
        )
        edge = compute_signal(
            _document([(0.0, 20.0, 1)], [(0.0, 5.0, "talk " * 8)]),
            {"still-001": StillText("Agenda", "", False)},
        )
        self.assertTrue(_row(under, "still-001")["prescore_zero"])
        self.assertFalse(_row(edge, "still-001")["prescore_zero"])


class VisitTests(unittest.TestCase):
    def test_revisit_counts_and_transition_links(self) -> None:
        document = _document(
            [
                (0, 10, 1),
                (10, 20, 2),
                (20, 30, 3),
                (30, 40, 2),
                (40, 50, 4),
                (50, 60, 2),
            ],
            [],
        )
        computed = compute_signal(document)
        two = _row(computed, "still-002")
        self.assertEqual(two["visit_count"], 3)
        self.assertTrue(two["revisited"])
        self.assertEqual(two["same_appearance"], ["still-004", "still-006"])
        self.assertEqual(two["transition_links"], ["still-003", "still-005"])
        for still_id in ("still-002", "still-004", "still-006"):
            self.assertTrue(_row(computed, still_id)["revisited"])
            self.assertEqual(_row(computed, still_id)["transition_links"], ["still-003", "still-005"])
        one = _row(computed, "still-001")
        self.assertEqual(one["visit_count"], 1)
        self.assertEqual(one["transition_links"], [])

    def test_pass_through_between_visits_merges_them(self) -> None:
        document = _document([(0, 10, 2), (10, 12, 9), (12, 22, 2)], [])
        computed = compute_signal(document)
        self.assertTrue(_row(computed, "still-002")["pass_through"])
        self.assertEqual(_row(computed, "still-001")["visit_count"], 1)
        self.assertFalse(_row(computed, "still-001")["revisited"])
        self.assertEqual(_row(computed, "still-002")["visit_count"], 0)

    def test_missing_appearance_is_null(self) -> None:
        document = _document([(0, 10), (10, 20)], [])
        computed = compute_signal(document)
        for row in computed.stills:
            self.assertIsNone(row["appearance"])
            self.assertIsNone(row["visit_count"])
            self.assertIsNone(row["revisited"])
            self.assertIsNone(row["same_appearance"])
            self.assertIsNone(row["transition_links"])
        self.assertIsNone(computed.payload["summary"]["revisited_appearance_count"])
        self.assertFalse(computed.payload["inputs"]["appearance_recorded"])


class TextSignalTests(unittest.TestCase):
    def test_tokens_stopwords_repeats_and_overlap(self) -> None:
        self.assertEqual(tokenize("The cat sat on the mat mat"), ["cat", "sat", "mat", "mat"])
        document = _document(
            [(0.0, 20.0, 1)],
            [(0.0, 10.0, "alpha beta spoken extra words density")],
        )
        overlap_row = _row(
            compute_signal(document, {"still-001": StillText("", "alpha beta gamma delta", False)}),
            "still-001",
        )
        self.assertEqual(overlap_row["token_count"], 4)
        self.assertEqual(overlap_row["content_overlap"], 0.5)
        repeats = _row(
            compute_signal(document, {"still-001": StillText("", "alpha alpha beta gamma", False)}),
            "still-001",
        )
        self.assertEqual(repeats["token_count"], 4)

    def test_empty_still_text_overlap_zero(self) -> None:
        document = _document([(0.0, 20.0, 1)], [(0.0, 10.0, "talk " * 8)])
        row = _row(
            compute_signal(document, {"still-001": StillText("", "", True)}),
            "still-001",
        )
        self.assertEqual(row["token_count"], 0)
        self.assertEqual(row["content_overlap"], 0.0)
        self.assertEqual(row["explanation_density"], round(10.0 / 1, 2))

    def test_tangent_boundaries(self) -> None:
        speech = "word " * 30
        document = _document([(0.0, 50.0, 1)], [(0.0, 45.01, speech)])
        sidecar = {"still-001": StillText("Page", "unrelated tokens here extra", False)}
        row = _row(compute_signal(document, sidecar), "still-001")
        self.assertTrue(row["suspect_tangent"])
        edge_time = _row(
            compute_signal(
                _document([(0.0, 50.0, 1)], [(0.0, 45.0, speech)]),
                sidecar,
            ),
            "still-001",
        )
        self.assertFalse(edge_time["suspect_tangent"])
        with_diagram = _row(
            compute_signal(
                document,
                {"still-001": StillText("Page", "unrelated tokens here extra", True)},
            ),
            "still-001",
        )
        self.assertFalse(with_diagram["suspect_tangent"])

    def test_absent_sidecar_entry_is_null(self) -> None:
        document = _document([(0.0, 10.0, 1), (10.0, 20.0, 2)], [(1.0, 4.0, "hello class this is speech")])
        computed = compute_signal(document, {"still-001": StillText("A", "text here", False)})
        missing = _row(computed, "still-002")
        for field in (
            "title",
            "has_diagram",
            "token_count",
            "explanation_density",
            "content_overlap",
            "suspect_tangent",
        ):
            self.assertIsNone(missing[field])


class EmphasisTests(unittest.TestCase):
    def test_exam_phrases_and_non_matches(self) -> None:
        document = _document(
            [(0.0, 20.0, 1)],
            [(2.0, 5.0, "This will be on the exam"), (6.0, 8.0, "please examine the figure")],
        )
        hits = _row(compute_signal(document), "still-001")["emphasis_hits"]
        phrases = [hit["phrase"] for hit in hits]
        self.assertEqual(phrases, ["exam", "will be on the"])
        self.assertEqual(hits[0]["at_seconds"], 2.0)
        self.assertEqual(hits[0]["cue_index"], 0)
        exams = _document([(0.0, 10.0, 1)], [(1.0, 3.0, "The exams are next week really")])
        exam_hits = [hit["phrase"] for hit in _row(compute_signal(exams), "still-001")["emphasis_hits"]]
        self.assertEqual(exam_hits, ["exams"])
        upper = _document([(0.0, 10.0, 1)], [(1.0, 3.0, "This is IMPORTANT to remember")])
        self.assertIn("important", [hit["phrase"] for hit in _row(compute_signal(upper), "still-001")["emphasis_hits"]])


class WindowTests(unittest.TestCase):
    def test_bounds_examples(self) -> None:
        self.assertEqual(window_bounds(10, 8, 4), [(1, 8), (5, 10)])
        self.assertEqual(window_bounds(8, 8, 4), [(1, 8)])
        self.assertEqual(window_bounds(3, 8, 4), [(1, 3)])
        self.assertEqual(window_bounds(16, 8, 4), [(1, 8), (5, 12), (9, 16)])
        self.assertEqual(window_bounds(17, 8, 4), [(1, 8), (5, 12), (9, 16), (13, 17)])

    def test_z_score_single_and_equal_and_pstdev(self) -> None:
        single = compute_signal(_document([(0, 10, 1)], [(0, 8, "talk " * 8)]))
        self.assertEqual(single.windows[0]["z_score"], 0.0)
        equal = compute_signal(
            _document(
                [(i * 10, (i + 1) * 10, i + 1) for i in range(16)],
                [(i * 10, i * 10 + 8, "talk " * 8) for i in range(16)],
            )
        )
        self.assertTrue(all(window["z_score"] == 0.0 for window in equal.windows))
        varied = compute_signal(
            _document(
                [(i * 10, (i + 1) * 10, i + 1) for i in range(16)],
                [
                    (i * 10, i * 10 + (8.0 if i < 8 else 4.0), "talk " * 8)
                    for i in range(16)
                ],
            )
        )
        means = [window["mean_raw"] for window in varied.windows]
        mu = statistics.mean(means)
        sigma = statistics.pstdev(means)
        for window in varied.windows:
            self.assertEqual(window["z_score"], round((window["mean_raw"] - mu) / sigma, 2))

    def test_peak_tie_and_all_boilerplate_window(self) -> None:
        document = _document([(0, 10, 1), (10, 20, 2)], [])
        computed = compute_signal(document)
        self.assertIsNone(computed.windows[0]["peak_still_id"])
        self.assertEqual(computed.windows[0]["spoken_seconds"], 0)
        self.assertEqual(computed.windows[0]["mean_spoken_seconds"], 0.0)
        tied = compute_signal(
            _document(
                [(0, 10, 1), (10, 20, 2)],
                [(0, 8, "talk " * 8), (10, 18, "talk " * 8)],
            )
        )
        self.assertEqual(tied.windows[0]["peak_still_id"], "still-001")

    def test_density_cutoff_and_high_signal_includes_revisited_boilerplate(self) -> None:
        speech = [(0, 8, "alpha beta gamma delta epsilon zeta")]
        stills = [(0, 10, 1), (10, 20, 2), (20, 30, 1)]
        sidecar = {
            "still-001": StillText("A", "alpha beta gamma", True),
            "still-002": StillText("B", "alpha beta gamma", True),
        }
        computed = compute_signal(
            _document(stills, speech + [(10, 18, "alpha beta gamma delta epsilon zeta")]),
            sidecar,
        )
        self.assertIsNone(computed.payload["summary"]["high_density_cutoff"])
        four = {
            f"still-{i:03d}": StillText("T", "alpha beta gamma", True) for i in range(1, 5)
        }
        four_doc = _document(
            [(i * 10, i * 10 + 10, i) for i in range(4)],
            [(i * 10, i * 10 + 8, "alpha beta gamma delta epsilon zeta") for i in range(4)],
        )
        four_computed = compute_signal(four_doc, four)
        densities = sorted(
            row["explanation_density"]
            for row in four_computed.stills
            if row["explanation_density"] is not None
        )
        self.assertEqual(four_computed.payload["summary"]["high_density_cutoff"], densities[2])
        revisited = compute_signal(
            _document(
                [(0, 10, 1), (10, 20, 2), (20, 30, 1)],
                [(0, 8, "talk " * 8), (10, 18, "talk " * 8)],
            )
        )
        high = revisited.windows[0]["high_signal_still_ids"]
        self.assertIn("still-003", high)
        self.assertTrue(_row(revisited, "still-003")["boilerplate"])
        self.assertTrue(_row(revisited, "still-003")["revisited"])


class SummaryTests(unittest.TestCase):
    def test_summary_rounds_raw_sums(self) -> None:
        document = _document([(0, 1.4, 1), (1.4, 2.8, 2), (2.8, 4.2, 3)], [])
        summary = compute_signal(document).payload["summary"]
        self.assertEqual(summary["elapsed_seconds"], 4)
        self.assertNotEqual(summary["elapsed_seconds"], 3)


class JsonContractTests(unittest.TestCase):
    def test_write_round_trip_and_generated_at(self) -> None:
        document = _document([(0, 10, 1), (10, 20, 2)], [(1, 4, "hello class this is speech")])
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            json_path, md_path = write_signal_views(document, folder)
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], SIGNAL_SCHEMA)
            self.assertTrue(payload["generated_at"].endswith("Z"))
            self.assertIn("T", payload["generated_at"])
            for key in (
                "document",
                "title",
                "duration_seconds",
                "inputs",
                "thresholds",
                "stills",
                "windows",
                "summary",
            ):
                self.assertIn(key, payload)
            self.assertTrue(md_path.is_file())

    def test_nan_duration_is_a_user_error(self) -> None:
        document = _document([(0.0, 10.0, 1)], [(1.0, 4.0, "hello class this is speech")])
        broken = LectureDocument(
            title=document.title,
            source=document.source,
            stills=(Still("still-001", 1, 0.0, float("nan"), "stills/still-001.png", 1),),
            transcript=document.transcript,
            sections=document.sections,
        )
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(PpsError):
                write_signal_views(broken, Path(raw))


class RenderTests(unittest.TestCase):
    def _five(self):
        return compute_signal(
            _document(
                [(0, 42, 1), (42, 223, 2), (223, 423, 3), (423, 426, 4), (426, 546, 2)],
                [
                    (0, 17, "agenda talk " * 5),
                    (50, 182, "deep explanation of the method " * 8),
                    (230, 421, "more derivation steps spoken out loud " * 6),
                    (430, 521, "return visit unpacking the same page " * 6),
                ],
            )
        )

    def test_histograms_are_ascii_with_legend_and_word_markers(self) -> None:
        computed = self._five()
        stills = render_still_histogram(computed)
        windows = render_window_histogram(computed)
        self.assertTrue(stills.splitlines()[0].startswith("Time per Still."))
        self.assertTrue(windows.splitlines()[0].startswith("Sliding windows of"))
        self.assertIn("boilerplate", stills.splitlines()[0])
        self.assertIn("pass-through", stills.splitlines()[0])
        self.assertIn("revisited (also N)", stills.splitlines()[0])
        self.assertTrue(all(ord(char) < 128 for char in stills))
        self.assertTrue(all(ord(char) < 128 for char in windows))
        header = stills.splitlines()[1]
        self.assertIn("Elapsed", header)
        self.assertIn("Spoken", header)
        self.assertGreater(header.index("Spoken"), header.index("Elapsed"))
        self.assertTrue(any(line.rstrip().endswith("s") or "  " in line for line in stills.splitlines()[2:]))

    def test_legend_tails_for_missing_inputs(self) -> None:
        none = compute_signal(_document([(0, 10)], [(1, 4, "hello class this is speech")]))
        legend = render_still_histogram(none).splitlines()[0]
        self.assertIn("Revisits: not recorded in this Document.", legend)
        self.assertIn("Still text: none; tangent? is never shown.", legend)

    def test_markdown_has_the_six_sections(self) -> None:
        document = _document([(0, 10, 1)], [(1, 4, "hello class this is speech")])
        text = render_signal_markdown(document, compute_signal(document))
        self.assertIn("# Test lecture: timing signal", text)
        self.assertIn("Generated ", text)
        self.assertIn("## Time per Still", text)
        self.assertIn("## Sliding windows", text)
        self.assertIn("## Per-Still table", text)
        self.assertIn("## Thresholds", text)

    def test_avg_grade_columns_only_with_grades(self) -> None:
        document = _document([(0, 10, 1), (10, 20, 2)], [(1, 8, "talk " * 8), (11, 18, "talk " * 8)])
        computed = compute_signal(document)
        plain = render_window_histogram(computed)
        self.assertNotIn("Avg grade", plain)
        grades = _valid_grades(document, computed)
        with_grades = render_window_histogram(computed, grades)
        self.assertIn("Avg grade", with_grades.splitlines()[0])
        self.assertIn("Avg grade", with_grades.splitlines()[1])


class CompareTests(unittest.TestCase):
    def test_compare_ignores_generated_at_and_reports_fields(self) -> None:
        document = _document([(0, 10, 1), (10, 20, 2)], [(1, 8, "talk " * 8), (11, 18, "talk " * 8)])
        computed = compute_signal(document).to_json_dict()
        stored = json.loads(json.dumps(computed))
        stored["generated_at"] = "1999-01-01T00:00:00Z"
        self.assertEqual(compare_signal(stored, computed), [])
        stored["stills"][0]["spoken_seconds"] = 150
        stored["windows"][0]["z_score"] = -0.20
        extra = dict(stored["stills"][1])
        extra["still_id"] = "still-099"
        stored["stills"].append(extra)
        stored["stills"] = [row for row in stored["stills"] if row["still_id"] != "still-002"]
        diffs = compare_signal(stored, computed)
        joined = "\n".join(diffs)
        self.assertIn("still-001 spoken_seconds: stored 150, recomputed", joined)
        self.assertIn("window 1-2 z_score: stored -0.2, recomputed", joined)
        self.assertTrue(any("still-002:" in line and "missing" in line for line in diffs))
        self.assertTrue(any("still-099:" in line for line in diffs))


class ValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = _document(
            [(0, 10, 1), (10, 20, 2), (20, 30, 3)],
            [(1, 8, "talk " * 8), (11, 18, "talk " * 8), (21, 28, "talk " * 8)],
        )
        self.computed = compute_signal(self.document)
        self.signal = self.computed.to_json_dict()
        self.grades = _valid_grades(self.document, self.computed)

    def test_valid_fixture_passes(self) -> None:
        self.assertEqual(validate_grades(self.document, self.signal, self.grades), [])

    def test_each_error_rule(self) -> None:
        cases = []
        bad_schema = json.loads(json.dumps(self.grades))
        bad_schema["schema"] = "nope"
        cases.append((bad_schema, "schema"))
        missing = json.loads(json.dumps(self.grades))
        missing["grades"] = missing["grades"][:2]
        cases.append((missing, "still-003"))
        unknown = json.loads(json.dumps(self.grades))
        unknown["grades"][0]["still_id"] = "still-099"
        cases.append((unknown, "still-099"))
        boolean = json.loads(json.dumps(self.grades))
        boolean["grades"][0]["importance"] = True
        cases.append((boolean, "importance"))
        category = json.loads(json.dumps(self.grades))
        category["grades"][0]["category"] = "critical_exam_skill"
        cases.append((category, "category"))
        skill = json.loads(json.dumps(self.grades))
        for item in skill["grades"]:
            if item["importance"] >= 2:
                item["actionable_skill"] = None
                break
        cases.append((skill, "actionable_skill"))
        fluff = json.loads(json.dumps(self.grades))
        for item in fluff["grades"]:
            if item["importance"] >= 2:
                item["fluff_filtered"] = True
                break
        cases.append((fluff, "fluff_filtered"))
        linked = json.loads(json.dumps(self.grades))
        linked["grades"][0]["linked_stills"] = [linked["grades"][0]["still_id"]]
        cases.append((linked, "linked_stills"))
        topic = json.loads(json.dumps(self.grades))
        topic["grades"][0]["core_topic"] = ""
        cases.append((topic, "core_topic"))
        module = json.loads(json.dumps(self.grades))
        module["module"] = "EE4704"
        module["knowledge_tree"] = None
        cases.append((module, "knowledge_tree"))
        for payload, needle in cases:
            with self.subTest(needle=needle):
                problems = validate_grades(self.document, self.signal, payload)
                self.assertTrue(problems, needle)
                self.assertTrue(any(needle in item for item in problems), problems)

    def test_warnings(self) -> None:
        short = json.loads(json.dumps(self.grades))
        short["grades"][0]["importance"] = 1
        short["grades"][0]["category"] = "low_yield_context"
        short["grades"][0]["actionable_skill"] = None
        short["grades"][0]["fluff_filtered"] = True
        warnings = warn_grades(self.document, self.signal, short)
        self.assertTrue(any("fluff_filtered" in item for item in warnings))
        zero = _document([(0, 2.5, 1)], [])
        computed = compute_signal(zero)
        grades = _valid_grades(zero, computed)
        grades["grades"][0]["importance"] = 2
        grades["grades"][0]["category"] = "core_testable_concept"
        grades["grades"][0]["actionable_skill"] = "do the thing"
        self.assertTrue(
            any("prescore_zero" in item for item in warn_grades(zero, computed.to_json_dict(), grades))
        )
        stale = json.loads(json.dumps(self.grades))
        stale["signal_generated_at"] = "1999-01-01T00:00:00Z"
        self.assertTrue(
            any("signal_generated_at" in item for item in warn_grades(self.document, self.signal, stale))
        )


class SidecarLoaderTests(unittest.TestCase):
    def test_loader_errors_and_partial(self) -> None:
        document = _document([(0, 10, 1), (10, 20, 2)], [])
        known = {still.id for still in document.stills}
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)

            def dump(name: str, payload) -> Path:
                path = folder / name
                path.write_text(json.dumps(payload), encoding="utf-8")
                return path

            unknown = dump(
                "unknown.json",
                {
                    "schema": STILLS_TEXT_SCHEMA,
                    "document": "lecture.json",
                    "written_by": "agent: test",
                    "stills": {"still-099": {"title": "", "text": "", "has_diagram": False}},
                },
            )
            with self.assertRaises(PpsError) as raised:
                load_stills_text(unknown, known)
            self.assertIn("still-099", str(raised.exception))
            not_bool = dump(
                "bool.json",
                {
                    "schema": STILLS_TEXT_SCHEMA,
                    "stills": {"still-001": {"title": "", "text": "", "has_diagram": "yes"}},
                },
            )
            with self.assertRaises(PpsError) as raised:
                load_stills_text(not_bool, known)
            self.assertIn("has_diagram", str(raised.exception))
            missing = dump("missing.json", {"schema": STILLS_TEXT_SCHEMA})
            with self.assertRaises(PpsError) as raised:
                load_stills_text(missing, known)
            self.assertIn("stills", str(raised.exception))
            schema = dump("schema.json", {"schema": "nope", "stills": {}})
            with self.assertRaises(PpsError) as raised:
                load_stills_text(schema, known)
            self.assertIn("schema", str(raised.exception))
            partial = dump(
                "partial.json",
                {
                    "schema": STILLS_TEXT_SCHEMA,
                    "stills": {"still-001": {"title": "A", "text": "body", "has_diagram": False}},
                },
            )
            loaded = load_stills_text(partial, known)
            self.assertEqual(set(loaded), {"still-001"})


class HistogramCliTests(unittest.TestCase):
    def test_default_prints_both_legends(self) -> None:
        document = _document([(0, 10, 1)], [(1, 4, "hello class this is speech")])
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            path = write_document(document, folder)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(["histogram", str(path)])
            self.assertEqual(code, 0)
            text = stdout.getvalue()
            self.assertIn("Time per Still.", text)
            self.assertIn("Sliding windows of", text)

    def test_check_write_and_mismatch(self) -> None:
        document = _document([(0, 10, 1)], [(1, 8, "talk " * 8)])
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            path = write_document(document, folder)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(["histogram", str(path), "--check"])
            self.assertEqual(code, 1)
            self.assertIn("no lecture.signal.json", stdout.getvalue())
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["histogram", str(path), "--write"]), 0)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(["histogram", str(folder), "--check"])
            self.assertEqual(code, 0)
            self.assertIn("Grades    none", stdout.getvalue())
            stored = json.loads((folder / SIGNAL_JSON).read_text(encoding="utf-8"))
            stored["stills"][0]["spoken_seconds"] = 150
            (folder / SIGNAL_JSON).write_text(json.dumps(stored, indent=2) + "\n", encoding="utf-8")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(["histogram", str(path), "--check"])
            self.assertEqual(code, 1)
            self.assertIn("still-001 spoken_seconds", stdout.getvalue())

    def test_check_malformed_grades_and_usage_errors(self) -> None:
        document = _document([(0, 10, 1)], [(1, 8, "talk " * 8)])
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            path = write_document(document, folder)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["histogram", str(path), "--write"]), 0)
            (folder / GRADES_JSON).write_text("{not json", encoding="utf-8")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(["histogram", str(path), "--check"])
            self.assertEqual(code, 1)
            self.assertIn("grades:", stdout.getvalue())
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = main(["histogram", str(path), "--check", "--write"])
            self.assertEqual(code, 2)
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = main(["histogram", str(path), "--check", "--window-size", "6"])
            self.assertEqual(code, 2)

    def test_check_valid_grades_appends_average_columns(self) -> None:
        document = _document([(0, 10, 1), (10, 20, 2)], [(1, 8, "talk " * 8), (11, 18, "talk " * 8)])
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            write_document(document, folder)
            computed = compute_signal(document)
            write_signal_views(document, folder)
            (folder / GRADES_JSON).write_text(
                json.dumps(_valid_grades(document, computed), indent=2) + "\n",
                encoding="utf-8",
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(["histogram", str(folder), "--check"])
            self.assertEqual(code, 0)
            text = stdout.getvalue()
            self.assertIn("Grades    valid", text)
            self.assertIn("Avg grade", text)

    def test_write_fills_text_signals_from_sidecar(self) -> None:
        document = _document([(0, 20, 1)], [(0, 10, "alpha beta spoken here extra words")])
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            write_document(document, folder)
            (folder / STILLS_TEXT_NAME).write_text(
                json.dumps(
                    {
                        "schema": STILLS_TEXT_SCHEMA,
                        "document": "lecture.json",
                        "written_by": "agent: test",
                        "stills": {
                            "still-001": {
                                "title": "Otsu",
                                "text": "alpha beta gamma delta",
                                "has_diagram": False,
                            }
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["histogram", str(folder), "--write"]), 0)
            payload = json.loads((folder / SIGNAL_JSON).read_text(encoding="utf-8"))
            self.assertEqual(payload["stills"][0]["token_count"], 5)
            self.assertIsNotNone(payload["stills"][0]["explanation_density"])
            self.assertTrue((folder / SIGNAL_MD).is_file())
            self.assertTrue((folder / BRIEF_NAME).name)
            self.assertTrue((folder / TAUGHT_NAME).name)
