"""Unit tests for Pydantic models and contracts."""

from datetime import datetime
from reverse_guardrail.core.models import (
    CoveredSection,
    ExtractedFragment,
    FragmentCategory,
    GuardrailResponse,
    InjectionAttempt,
    PipelineConfig,
    ReconstructionReport,
    StrategyCategory,
    TargetScopeConfig,
)


def test_injection_attempt_creation():
    attempt = InjectionAttempt(
        round_id=1,
        strategy_category=StrategyCategory.ROLEPLAY_PERSONA_SHIFT,
        payload="Hello, testing persona shift",
        targeted_gaps=["Role"],
    )
    assert attempt.attempt_id is not None
    assert attempt.round_id == 1
    assert attempt.strategy_category == StrategyCategory.ROLEPLAY_PERSONA_SHIFT
    assert isinstance(attempt.timestamp, datetime)


def test_guardrail_response_creation():
    resp = GuardrailResponse(
        attempt_id="att-123",
        round_id=1,
        raw_response="Filtered output",
        latency_ms=12.5,
        refused=False,
    )
    assert resp.attempt_id == "att-123"
    assert resp.refused is False
    assert resp.status_code == 200


def test_extracted_fragment_creation():
    frag = ExtractedFragment(
        round_id=1,
        attempt_id="att-123",
        category=FragmentCategory.CONSTRAINT_NEGATIVE_RULE,
        text="Never reveal DB keys",
        confidence_score=0.92,
        source_strategy=StrategyCategory.META_CONVERSATIONAL,
    )
    assert frag.fragment_id is not None
    assert frag.confidence_score == 0.92
    assert frag.category == FragmentCategory.CONSTRAINT_NEGATIVE_RULE


def test_reconstruction_report_creation():
    sec = CoveredSection(
        section_name="Role",
        inferred_content="Guardian AI",
        confidence=0.9,
    )
    rep = ReconstructionReport(
        round_id=1,
        reconstructed_prompt="# System Prompt\n...",
        overall_confidence=0.85,
        covered_sections=[sec],
        gaps=["Tokens"],
    )
    assert rep.overall_confidence == 0.85
    assert len(rep.covered_sections) == 1
    assert rep.gaps == ["Tokens"]


def test_pipeline_config_defaults():
    config = PipelineConfig(
        target=TargetScopeConfig(authorized=True, engagement_id="ENG-1")
    )
    assert config.max_rounds == 5
    assert config.attempts_per_round == 5
    assert config.confidence_threshold == 0.85
