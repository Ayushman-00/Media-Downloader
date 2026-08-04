"""
Tests for the multi-dimensional virality scoring system.

Tests all 5 heuristic dimension scorers (pure functions, no FFmpeg),
LLM response parsers, score blending, and backward compatibility.
"""
import json
import pytest
import sys
import os

# Ensure imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.highlight_finder import (
    _score_hook,
    _score_flow,
    _score_engagement,
    _score_value,
    _score_trend,
    compute_virality_score,
    blend_scores,
    score_heuristic,
    _parse_dimension_scores,
    _parse_index_list,
    make_windows,
    DEFAULT_WEIGHTS,
    _get_scoring_config,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def high_hook_window():
    """Window with a strong hook opening."""
    return {
        "start": 10.0,
        "end": 55.0,
        "text": "What if I told you the biggest secret in tech? Nobody talks about this. It's actually insane how this works.",
        "segments": [
            {"start": 10.0, "end": 15.0, "text": "What if I told you the biggest secret in tech?"},
            {"start": 15.0, "end": 25.0, "text": "Nobody talks about this."},
            {"start": 25.0, "end": 55.0, "text": "It's actually insane how this works."},
        ],
    }


@pytest.fixture
def weak_hook_window():
    """Window with a weak/generic opening."""
    return {
        "start": 100.0,
        "end": 145.0,
        "text": "So um yeah I was just kind of thinking about what we were discussing earlier and it seems like there might be some things that are worth considering when you look at the broader landscape of how people approach these kinds of situations in general.",
        "segments": [
            {"start": 100.0, "end": 145.0, "text": "So um yeah I was just kind of thinking about what we were discussing earlier and it seems like there might be some things that are worth considering when you look at the broader landscape of how people approach these kinds of situations in general."},
        ],
    }


@pytest.fixture
def high_value_window():
    """Window with strong practical value."""
    return {
        "start": 30.0,
        "end": 75.0,
        "text": "Here's how to do this in 3 steps. Step 1: identify the problem. Step 2: apply the solution. Step 3: measure the results. Pro tip: always track your progress with numbers.",
        "segments": [
            {"start": 30.0, "end": 45.0, "text": "Here's how to do this in 3 steps."},
            {"start": 45.0, "end": 55.0, "text": "Step 1: identify the problem."},
            {"start": 55.0, "end": 65.0, "text": "Step 2: apply the solution."},
            {"start": 65.0, "end": 75.0, "text": "Step 3: measure the results. Pro tip: always track your progress with numbers."},
        ],
    }


@pytest.fixture
def high_engagement_window():
    """Window with strong emotional engagement."""
    return {
        "start": 50.0,
        "end": 95.0,
        "text": "I was absolutely furious! Can you believe what happened? It was shocking and totally unexpected. The plot twist? They actually loved it! Are you serious? No way!",
        "segments": [
            {"start": 50.0, "end": 60.0, "text": "I was absolutely furious!"},
            {"start": 60.0, "end": 70.0, "text": "Can you believe what happened?"},
            {"start": 70.0, "end": 80.0, "text": "It was shocking and totally unexpected."},
            {"start": 80.0, "end": 90.0, "text": "The plot twist? They actually loved it!"},
            {"start": 90.0, "end": 95.0, "text": "Are you serious? No way!"},
        ],
    }


@pytest.fixture
def flat_window():
    """Window with minimal engagement/value."""
    return {
        "start": 200.0,
        "end": 245.0,
        "text": "and then we moved on to the next topic which was also interesting and we talked about that for a while",
        "segments": [
            {"start": 200.0, "end": 245.0, "text": "and then we moved on to the next topic which was also interesting and we talked about that for a while"},
        ],
    }


# ---------------------------------------------------------------------------
# Tests: Hook scoring
# ---------------------------------------------------------------------------

class TestHookScore:
    def test_strong_hook_scores_high(self, high_hook_window):
        score = _score_hook(high_hook_window)
        assert score >= 50, f"Strong hook should score >= 50, got {score}"

    def test_weak_hook_scores_low(self, weak_hook_window):
        score = _score_hook(weak_hook_window)
        assert score <= 30, f"Weak hook should score <= 30, got {score}"

    def test_question_opening_boosts(self):
        window = {
            "start": 0, "end": 45,
            "text": "Did you know this one crazy fact? It will blow your mind.",
            "segments": [],
        }
        score = _score_hook(window)
        assert score >= 40, f"Question opener should boost, got {score}"

    def test_empty_text_returns_zero(self):
        window = {"start": 0, "end": 45, "text": "", "segments": []}
        assert _score_hook(window) == 0

    def test_score_bounded_0_100(self, high_hook_window):
        score = _score_hook(high_hook_window)
        assert 0 <= score <= 100


# ---------------------------------------------------------------------------
# Tests: Flow scoring
# ---------------------------------------------------------------------------

class TestFlowScore:
    def test_clean_boundaries_score_high(self, high_value_window):
        score = _score_flow(high_value_window)
        assert score >= 40, f"Clean boundaries should score >= 40, got {score}"

    def test_mid_sentence_start_penalized(self):
        window = {
            "start": 12.5, "end": 57.5,
            "text": "about this topic and I think it's really important because we need to understand how things work in the modern world.",
            "segments": [
                {"start": 10.0, "end": 30.0, "text": "about this topic and I think it's really important"},
                {"start": 30.0, "end": 57.5, "text": "because we need to understand how things work in the modern world."},
            ],
        }
        score = _score_flow(window)
        # Mid-sentence start (lowercase first char, offset from seg boundary)
        assert score <= 60

    def test_empty_window_returns_zero(self):
        window = {"start": 0, "end": 0, "text": "", "segments": []}
        assert _score_flow(window) == 0

    def test_consistent_pacing_scores_higher(self, high_value_window):
        score_good = _score_flow(high_value_window)
        # Window with very uneven pacing
        bad_window = {
            "start": 0, "end": 45,
            "text": "Hello. " + " ".join(["word"] * 100),
            "segments": [
                {"start": 0, "end": 5, "text": "Hello."},
                {"start": 5, "end": 15, "text": ""},
                {"start": 15, "end": 45, "text": " ".join(["word"] * 100)},
            ],
        }
        score_bad = _score_flow(bad_window)
        assert score_good >= score_bad


# ---------------------------------------------------------------------------
# Tests: Engagement scoring
# ---------------------------------------------------------------------------

class TestEngagementScore:
    def test_emotional_content_scores_high(self, high_engagement_window):
        score = _score_engagement(high_engagement_window)
        assert score >= 50, f"High engagement should score >= 50, got {score}"

    def test_flat_content_scores_low(self, flat_window):
        score = _score_engagement(flat_window)
        assert score <= 30, f"Flat content should score <= 30, got {score}"

    def test_questions_boost_engagement(self):
        window = {
            "start": 0, "end": 45,
            "text": "Why do people do this? What's the point? Don't you think it's weird?",
            "segments": [],
        }
        score = _score_engagement(window)
        assert score >= 15, f"Multiple questions should boost engagement"

    def test_empty_text_returns_zero(self):
        window = {"start": 0, "end": 45, "text": "", "segments": []}
        assert _score_engagement(window) == 0


# ---------------------------------------------------------------------------
# Tests: Value scoring
# ---------------------------------------------------------------------------

class TestValueScore:
    def test_instructional_content_scores_high(self, high_value_window):
        score = _score_value(high_value_window)
        assert score >= 50, f"Instructional content should score >= 50, got {score}"

    def test_generic_content_scores_low(self, flat_window):
        score = _score_value(flat_window)
        assert score <= 30, f"Generic content should score <= 30, got {score}"

    def test_list_patterns_detected(self):
        window = {
            "start": 0, "end": 45,
            "text": "Here are 5 tips to improve your workflow. Number 1 is the most important.",
            "segments": [],
        }
        score = _score_value(window)
        assert score >= 20, f"List patterns should be detected"

    def test_numbers_boost_value(self):
        window = {
            "start": 0, "end": 45,
            "text": "We increased revenue by 47% in just 3 months using 2 simple strategies.",
            "segments": [],
        }
        score = _score_value(window)
        assert score >= 10, f"Numbers/data should boost value score"


# ---------------------------------------------------------------------------
# Tests: Trend scoring
# ---------------------------------------------------------------------------

class TestTrendScore:
    def test_trending_topic_scores_high(self):
        window = {
            "start": 0, "end": 45,
            "text": "AI and artificial intelligence are changing everything about productivity and technology. This is the future of entrepreneurship.",
            "segments": [],
        }
        score = _score_trend(window)
        assert score >= 30, f"Trending topics should score >= 30, got {score}"

    def test_generic_topic_scores_lower(self, flat_window):
        score = _score_trend(flat_window)
        assert score <= 30

    def test_shareability_language_boosts(self):
        window = {
            "start": 0, "end": 45,
            "text": "You won't believe this hack. Share this with everyone. Save this for later!",
            "segments": [],
        }
        score = _score_trend(window)
        assert score >= 20


# ---------------------------------------------------------------------------
# Tests: Composite scoring
# ---------------------------------------------------------------------------

class TestCompositeScore:
    def test_default_weights_sum_to_one(self):
        total = sum(DEFAULT_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001, f"Weights must sum to 1.0, got {total}"

    def test_all_100s_give_100(self):
        scores = {"hook": 100, "flow": 100, "engagement": 100, "value": 100, "trend": 100}
        assert compute_virality_score(scores) == 100

    def test_all_0s_give_0(self):
        scores = {"hook": 0, "flow": 0, "engagement": 0, "value": 0, "trend": 0}
        assert compute_virality_score(scores) == 0

    def test_weighted_correctly(self):
        # Hook=100, everything else=0 → should be 30 (0.30 weight)
        scores = {"hook": 100, "flow": 0, "engagement": 0, "value": 0, "trend": 0}
        result = compute_virality_score(scores)
        assert result == 30

    def test_custom_weights(self):
        scores = {"hook": 100, "flow": 0, "engagement": 0, "value": 0, "trend": 0}
        custom_weights = {"hook": 1.0, "flow": 0, "engagement": 0, "value": 0, "trend": 0}
        result = compute_virality_score(scores, custom_weights)
        assert result == 100

    def test_score_bounded(self):
        scores = {"hook": 150, "flow": 200, "engagement": 300, "value": 400, "trend": 500}
        result = compute_virality_score(scores)
        assert 0 <= result <= 100


# ---------------------------------------------------------------------------
# Tests: Score blending
# ---------------------------------------------------------------------------

class TestBlendScores:
    def test_pure_heuristic(self):
        h = {"hook": 80, "flow": 70, "engagement": 60, "value": 50, "trend": 40}
        l = {"hook": 0, "flow": 0, "engagement": 0, "value": 0, "trend": 0}
        composite, blended = blend_scores(h, l, llm_weight=0.0)
        assert blended == h

    def test_pure_llm(self):
        h = {"hook": 0, "flow": 0, "engagement": 0, "value": 0, "trend": 0}
        l = {"hook": 90, "flow": 80, "engagement": 70, "value": 60, "trend": 50}
        composite, blended = blend_scores(h, l, llm_weight=1.0)
        assert blended == l

    def test_50_50_blend(self):
        h = {"hook": 100, "flow": 100, "engagement": 100, "value": 100, "trend": 100}
        l = {"hook": 0, "flow": 0, "engagement": 0, "value": 0, "trend": 0}
        composite, blended = blend_scores(h, l, llm_weight=0.5)
        for dim in DEFAULT_WEIGHTS:
            assert blended[dim] == 50

    def test_default_blend_ratio(self):
        h = {"hook": 100, "flow": 100, "engagement": 100, "value": 100, "trend": 100}
        l = {"hook": 100, "flow": 100, "engagement": 100, "value": 100, "trend": 100}
        composite, blended = blend_scores(h, l)
        assert composite == 100


# ---------------------------------------------------------------------------
# Tests: LLM response parsing
# ---------------------------------------------------------------------------

class TestParseDimensionScores:
    def test_parse_structured_json(self):
        raw = json.dumps([
            {"index": 0, "hook": 85, "flow": 72, "engagement": 80, "value": 65, "trend": 70, "rationale": "test"},
            {"index": 1, "hook": 60, "flow": 55, "engagement": 40, "value": 30, "trend": 45, "rationale": "test2"},
        ])
        result = _parse_dimension_scores(raw, max_idx=1)
        assert len(result) == 2
        assert result[0]["hook"] == 85
        assert result[1]["engagement"] == 40

    def test_parse_with_code_fences(self):
        raw = "```json\n" + json.dumps([
            {"index": 0, "hook": 90, "flow": 80, "engagement": 70, "value": 60, "trend": 50}
        ]) + "\n```"
        result = _parse_dimension_scores(raw, max_idx=0)
        assert len(result) == 1
        assert result[0]["hook"] == 90

    def test_fallback_to_index_list(self):
        raw = "[2, 0, 1]"
        result = _parse_dimension_scores(raw, max_idx=2)
        assert len(result) == 3
        # First ranked should have highest fake scores
        assert result[0]["index"] == 2

    def test_clamps_scores_to_0_100(self):
        raw = json.dumps([
            {"index": 0, "hook": 150, "flow": -10, "engagement": 50, "value": 50, "trend": 50}
        ])
        result = _parse_dimension_scores(raw, max_idx=0)
        assert result[0]["hook"] == 100
        assert result[0]["flow"] == 0

    def test_filters_invalid_indices(self):
        raw = json.dumps([
            {"index": 0, "hook": 50, "flow": 50, "engagement": 50, "value": 50, "trend": 50},
            {"index": 99, "hook": 50, "flow": 50, "engagement": 50, "value": 50, "trend": 50},
        ])
        result = _parse_dimension_scores(raw, max_idx=5)
        assert len(result) == 1
        assert result[0]["index"] == 0

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError):
            _parse_dimension_scores("not json at all", max_idx=5)


# ---------------------------------------------------------------------------
# Tests: Backward compatibility
# ---------------------------------------------------------------------------

class TestBackwardCompat:
    def test_score_field_present(self, high_hook_window):
        """score_heuristic must still produce a 'score' field for backward compat."""
        windows = [high_hook_window]
        # No video_path needed for text-only scoring (audio returns fallback 0.5)
        result = score_heuristic("nonexistent.mp4", windows)
        assert len(result) == 1
        assert "score" in result[0]
        assert "virality_score" in result[0]
        assert result[0]["score"] == result[0]["virality_score"]

    def test_scores_dict_present(self, high_hook_window):
        """Each result should have a 'scores' dict with all 5 dimensions."""
        windows = [high_hook_window]
        result = score_heuristic("nonexistent.mp4", windows)
        assert "scores" in result[0]
        for dim in DEFAULT_WEIGHTS:
            assert dim in result[0]["scores"]

    def test_sorted_by_virality_score(self, high_hook_window, flat_window):
        """Results should be sorted best-first."""
        windows = [flat_window, high_hook_window]
        result = score_heuristic("nonexistent.mp4", windows)
        assert result[0]["virality_score"] >= result[1]["virality_score"]


# ---------------------------------------------------------------------------
# Tests: get_scoring_config
# ---------------------------------------------------------------------------

class TestScoringConfig:
    def test_defaults_when_no_cfg(self):
        cfg = _get_scoring_config(None)
        assert cfg["weights"] == DEFAULT_WEIGHTS
        assert cfg["llm_weight"] == 0.60

    def test_custom_weights(self):
        cfg = _get_scoring_config({
            "highlight": {
                "scoring": {
                    "weights": {"hook": 0.50, "flow": 0.10, "engagement": 0.10, "value": 0.15, "trend": 0.15},
                    "llm_weight": 0.80,
                }
            }
        })
        assert cfg["weights"]["hook"] == 0.50
        assert cfg["llm_weight"] == 0.80

    def test_missing_keys_get_defaults(self):
        cfg = _get_scoring_config({
            "highlight": {
                "scoring": {
                    "weights": {"hook": 0.40},
                }
            }
        })
        # hook overridden
        assert cfg["weights"]["hook"] == 0.40
        # others defaulted
        assert cfg["weights"]["flow"] == 0.20


# ---------------------------------------------------------------------------
# Tests: parse_index_list (backward compat)
# ---------------------------------------------------------------------------

class TestParseIndexList:
    def test_basic_list(self):
        result = _parse_index_list("[2, 0, 4, 1, 3]", max_idx=4)
        assert result == [2, 0, 4, 1, 3]

    def test_with_fences(self):
        result = _parse_index_list("```json\n[1, 0]\n```", max_idx=1)
        assert result == [1, 0]

    def test_filters_out_of_range(self):
        result = _parse_index_list("[0, 1, 99]", max_idx=5)
        assert 99 not in result
