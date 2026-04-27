"""Tests for agency.eval_harness."""

from __future__ import annotations

import pytest

from agency.eval_harness import (
    EvalCase,
    CaseResult,
    Report,
    EvalSuite,
    check_substring,
    check_regex,
    check_routing_slug,
    routing_suite,
    ROUTING_SUITE_CASES,
)


# ---------------------------------------------------------------------------
# Check helpers
# ---------------------------------------------------------------------------


def test_check_substring_case_insensitive():
    assert check_substring("Hello World", "hello") is True
    assert check_substring("Hello World", "WORLD") is True
    assert check_substring("Hello World", "missing") is False


def test_check_regex_finds_pattern():
    assert check_regex("foo123bar", r"\d+") is True
    assert check_regex("abc", r"\d+") is False


def test_check_routing_slug_with_string():
    assert check_routing_slug("foo", "foo") is True
    assert check_routing_slug("foo", "bar") is False


def test_check_routing_slug_with_dict():
    assert check_routing_slug({"skill": "x"}, "x") is True
    assert check_routing_slug({"slug": "x"}, "x") is True
    assert check_routing_slug({"skill": "x"}, "y") is False


def test_check_routing_slug_none_is_false():
    assert check_routing_slug(None, "anything") is False


def test_check_routing_slug_object_with_skill():
    class Fake:
        class skill:
            slug = "alpha"
    assert check_routing_slug(Fake(), "alpha") is True
    assert check_routing_slug(Fake(), "beta") is False


# ---------------------------------------------------------------------------
# EvalSuite — core flow
# ---------------------------------------------------------------------------


def test_run_returns_report_with_pass_rate():
    cases = [
        EvalCase(case_id="a", input="x", must_include=("x",)),
        EvalCase(case_id="b", input="y", must_include=("y",)),
        EvalCase(case_id="c", input="z", must_include=("z",)),
    ]
    suite = EvalSuite("demo", cases)
    report = suite.run(lambda inp: inp)
    assert report.total == 3
    assert report.passed == 3
    assert report.pass_rate == 1.0
    assert report.average_score == 1.0


def test_failing_assertion_marks_case_failed():
    cases = [EvalCase(case_id="x", input="hi", must_include=("nope",))]
    report = EvalSuite("demo", cases).run(lambda inp: inp)
    assert report.passed == 0
    assert report.cases[0].passed is False


def test_must_not_include_blocks_substring():
    cases = [EvalCase(case_id="x", input="hi", must_not_include=("hi",))]
    report = EvalSuite("demo", cases).run(lambda inp: inp)
    assert report.passed == 0


def test_must_match_regex():
    cases = [EvalCase(case_id="x", input="abc123", must_match=(r"\d+",))]
    report = EvalSuite("demo", cases).run(lambda inp: inp)
    assert report.passed == 1


def test_callable_error_marks_case_failed():
    def bad(_):
        raise RuntimeError("boom")

    cases = [EvalCase(case_id="x", input="anything")]
    report = EvalSuite("demo", cases).run(bad)
    assert report.passed == 0
    assert report.cases[0].error == "boom"


def test_no_assertions_passes_when_no_error():
    cases = [EvalCase(case_id="x", input="anything")]
    report = EvalSuite("demo", cases).run(lambda inp: inp)
    assert report.passed == 1


def test_report_summary_line_includes_counts():
    cases = [EvalCase(case_id="a", input="x", must_include=("x",))]
    report = EvalSuite("demo", cases).run(lambda inp: inp)
    line = report.summary_line()
    assert "demo" in line
    assert "1/1" in line


def test_report_to_dict_serializes():
    cases = [EvalCase(case_id="a", input="x")]
    report = EvalSuite("demo", cases).run(lambda inp: inp)
    out = report.to_dict()
    for k in ("suite_name", "total", "passed", "pass_rate", "cases"):
        assert k in out


def test_case_result_to_dict_round_trip():
    r = CaseResult("a", True, 1.0, {"x": True}, "foo", 1.5)
    out = r.to_dict()
    assert out["case_id"] == "a"
    assert out["passed"] is True


def test_from_dict_list_constructs_suite():
    raw = [{"input": "hi", "must_include": ["hi"]}, {"input": "bye"}]
    suite = EvalSuite.from_dict_list("demo", raw)
    assert len(suite.cases) == 2
    assert suite.cases[0].must_include == ("hi",)


def test_pass_rate_zero_for_empty_report():
    rep = Report("empty", [], 0, 1)
    assert rep.pass_rate == 0.0
    assert rep.average_score == 0.0


# ---------------------------------------------------------------------------
# Routing suite
# ---------------------------------------------------------------------------


def test_routing_suite_has_cases():
    suite = routing_suite()
    assert len(suite.cases) == len(ROUTING_SUITE_CASES)
    for case in suite.cases:
        assert case.expected_slug


def test_routing_suite_runs_against_real_brain():
    from agency.jarvis_brain import get_brain

    brain = get_brain()
    suite = routing_suite()
    report = suite.run(lambda req: brain.skill_for(req).to_dict())
    # Should pass at least 80% of cases against the real router.
    assert report.pass_rate >= 0.8


def test_weight_amplifies_score():
    cases = [EvalCase(case_id="x", input="hi", must_include=("hi",), weight=2.0)]
    report = EvalSuite("demo", cases).run(lambda inp: inp)
    assert report.cases[0].score == pytest.approx(2.0)
