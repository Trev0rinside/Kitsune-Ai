"""Core data models and Pydantic contracts for Reverse-Guardrail."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field, field_validator


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StrategyCategory(str, Enum):
    """Categories of soft injection strategies used by the Tester Agent."""
    DIRECT_OVERRIDE = "direct_override"
    ROLEPLAY_PERSONA_SHIFT = "roleplay_persona_shift"
    MULTITURN_INCREMENTAL = "multiturn_incremental"
    FORMAT_MANIPULATION = "format_manipulation"
    META_CONVERSATIONAL = "meta_conversational"
    HYPOTHETICAL_SCENARIO = "hypothetical_scenario"
    ERROR_ELICITATION = "error_elicitation"


class FragmentCategory(str, Enum):
    """Classification categories for leaked system prompt fragments."""
    INSTRUCTION = "instruction"
    CONSTRAINT_NEGATIVE_RULE = "constraint_negative_rule"
    TOOL_REFERENCE = "tool_reference"
    REFUSAL_PATTERN = "refusal_pattern"
    FORMATTING_RULE = "formatting_rule"
    ROLE_PERSONA = "role_persona"
    SECURITY_TOKEN = "security_token"
    UNKNOWN = "unknown"


class PipelineStatus(str, Enum):
    """Status enum for the orchestration pipeline run."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED_UNAUTHORIZED = "aborted_unauthorized"


class TargetScopeConfig(BaseModel):
    """Scope authorization configuration - acts as the non-negotiable kill-switch."""
    authorized: bool = Field(
        False,
        description="Explicit authorization flag from the guardrail owner.",
    )
    engagement_id: str = Field(
        "",
        description="Non-empty tracking ID for the authorized security assessment.",
    )
    target_name: str = Field(
        "default_target",
        description="Human readable identifier for the target system.",
    )
    target_url: Optional[str] = Field(
        None,
        description="Target endpoint URL (HTTP/REST or Web UI).",
    )
    custom_headers: Dict[str, str] = Field(
        default_factory=dict,
        description="Custom headers (e.g. Bearer auth, custom tenant ID).",
    )
    # Browser Target Options
    use_browser: bool = Field(
        False,
        description="Enable browser automation (Playwright/browser-use) to test web chat interfaces.",
    )
    cookies: Optional[Any] = Field(
        None,
        description="Session cookies (list of dicts, JSON string, or Cookie header) for authenticated browsing.",
    )
    input_selector: Optional[str] = Field(
        None,
        description="CSS/XPath selector for the chat input field (auto-detected if None).",
    )
    submit_selector: Optional[str] = Field(
        None,
        description="CSS/XPath selector for send button (uses Enter key if None).",
    )
    response_selector: Optional[str] = Field(
        None,
        description="CSS/XPath selector for assistant message bubbles (auto-detected if None).",
    )
    headless: bool = Field(
        True,
        description="Run browser in headless mode.",
    )

    @field_validator("engagement_id")
    @classmethod
    def validate_engagement_id(cls, v: str) -> str:
        if v is not None:
            return v.strip()
        return ""


class InjectionAttempt(BaseModel):
    """Pydantic contract for an injection attempt dispatched from Tester to Guardrail."""
    attempt_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique identifier for this injection attempt.",
    )
    round_id: int = Field(
        ...,
        ge=1,
        description="1-indexed orchestration round number.",
    )
    strategy_category: StrategyCategory = Field(
        ...,
        description="The soft injection category used.",
    )
    payload: str = Field(
        ...,
        description="The actual text prompt sent to the guardrail target.",
    )
    timestamp: datetime = Field(
        default_factory=_utc_now,
        description="Timestamp when the attempt was generated.",
    )
    targeted_gaps: List[str] = Field(
        default_factory=list,
        description="Specific prompt sections/gaps targeted in this attempt.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary execution metadata.",
    )


class GuardrailResponse(BaseModel):
    """Pydantic contract for the target Guardrail's response."""
    attempt_id: str = Field(
        ...,
        description="ID of the matching injection attempt.",
    )
    round_id: int = Field(
        ...,
        description="Round number.",
    )
    raw_response: str = Field(
        ...,
        description="Raw output returned by the Guardrail.",
    )
    latency_ms: float = Field(
        ...,
        ge=0.0,
        description="Execution latency in milliseconds.",
    )
    refused: bool = Field(
        ...,
        description="True if the Guardrail explicitly blocked/refused the request.",
    )
    status_code: int = Field(
        200,
        description="HTTP or target status code.",
    )
    error_message: Optional[str] = Field(
        None,
        description="Error details if execution failed.",
    )
    timestamp: datetime = Field(
        default_factory=_utc_now,
        description="Timestamp of response receipt.",
    )


class ExtractedFragment(BaseModel):
    """Pydantic contract for an information fragment extracted by the Inspectioner Agent."""
    fragment_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique ID of the extracted fragment.",
    )
    round_id: int = Field(
        ...,
        description="Round number when the fragment was discovered.",
    )
    attempt_id: str = Field(
        ...,
        description="Attempt that triggered the leak.",
    )
    category: FragmentCategory = Field(
        ...,
        description="Classified category of the leaked content.",
    )
    text: str = Field(
        ...,
        description="The atomic instruction, rule, or constraint text.",
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Inspectioner confidence score [0.0 - 1.0].",
    )
    source_strategy: StrategyCategory = Field(
        ...,
        description="Injection strategy that produced this leak.",
    )
    context_snippet: Optional[str] = Field(
        None,
        description="Surrounding text or justification for the extraction.",
    )
    timestamp: datetime = Field(
        default_factory=_utc_now,
        description="Timestamp of extraction.",
    )


class CoveredSection(BaseModel):
    """A section of the system prompt inferred by the Reverse Prompt Engineer."""
    section_name: str = Field(
        ...,
        description="Name of the section (e.g. Identity, Constraints, Tooling).",
    )
    inferred_content: str = Field(
        ...,
        description="Reconstructed instructions for this section.",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Section-specific confidence score.",
    )
    supporting_fragment_ids: List[str] = Field(
        default_factory=list,
        description="List of fragment IDs that support this reconstruction.",
    )


class ReconstructionReport(BaseModel):
    """Pydantic contract for the system prompt reconstruction report."""
    report_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique report identifier.",
    )
    round_id: int = Field(
        ...,
        description="Round at which this report was generated.",
    )
    reconstructed_prompt: str = Field(
        ...,
        description="Full synthesized markdown/text of the reconstructed system prompt.",
    )
    overall_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Aggregate confidence score [0.0 - 1.0].",
    )
    covered_sections: List[CoveredSection] = Field(
        default_factory=list,
        description="Breakdown of covered prompt sections.",
    )
    gaps: List[str] = Field(
        default_factory=list,
        description="Residual gaps and missing areas to target in subsequent rounds.",
    )
    fragments_used: List[str] = Field(
        default_factory=list,
        description="IDs of fragments utilized in synthesis.",
    )
    timestamp: datetime = Field(
        default_factory=_utc_now,
        description="Report timestamp.",
    )


class PipelineConfig(BaseModel):
    """Configuration for a Reverse-Guardrail pipeline run."""
    target: TargetScopeConfig = Field(
        default_factory=TargetScopeConfig,
        description="Scope authorization configuration (Gatekeeper).",
    )
    max_rounds: int = Field(
        5,
        ge=1,
        le=50,
        description="Maximum number of iterative testing rounds.",
    )
    attempts_per_round: int = Field(
        5,
        ge=1,
        le=50,
        description="Number of injection attempts generated per round.",
    )
    report_frequency_rounds: int = Field(
        1,
        ge=1,
        description="Generate a reconstruction report every K rounds.",
    )
    confidence_threshold: float = Field(
        0.85,
        ge=0.0,
        le=1.0,
        description="Stop condition: confidence threshold to consider prompt fully recovered.",
    )
    stagnation_patience_rounds: int = Field(
        3,
        ge=1,
        description="Stop condition: max consecutive rounds with 0 new fragments.",
    )
    rate_limit_rps: float = Field(
        2.0,
        gt=0.0,
        description="Max requests per second sent to the Guardrail.",
    )
    timeout_seconds: float = Field(
        15.0,
        gt=0.0,
        description="Per-request timeout in seconds.",
    )
    models: Dict[str, str] = Field(
        default_factory=lambda: {
            "tester": "mock-tester",
            "inspectioner": "mock-inspectioner",
            "reverse_engineer": "mock-reverse-engineer",
            "vulnerability_analyzer": "mock-vulnerability-analyzer",
            "hardening_reporter": "mock-hardening-reporter",
        },
        description="LLM model identifiers for each agent.",
    )


class RoundSummary(BaseModel):
    """Summary of a single completed round."""
    round_id: int
    attempts_count: int
    refusals_count: int
    fragments_extracted_count: int
    new_fragments_count: int
    current_confidence: float
    gaps_count: int
    timestamp: datetime = Field(default_factory=_utc_now)


class AuditLogEntry(BaseModel):
    """Structured audit log entry for security traceability."""
    entry_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=_utc_now)
    engagement_id: str
    action: str
    status: str
    details: Dict[str, Any] = Field(default_factory=dict)


# ==============================================================================
# Phase 2: Vulnerability Assessment & Defensive Hardening Models
# ==============================================================================


class VulnerabilitySeverity(str, Enum):
    """Severity ratings for identified system prompt vulnerabilities."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class VulnerabilityCategory(str, Enum):
    """Taxonomy of system prompt architectural weaknesses aligned with OWASP LLM Top 10."""
    MISSING_DELIMITER = "missing_delimiter"
    WEAK_NEGATION = "weak_negation"
    SECRET_EXPOSURE = "secret_exposure"
    PRECEDENCE_CONFLICT = "precedence_conflict"
    INSTRUCTION_DRIFT_RISK = "instruction_drift_risk"
    MISSING_OUTPUT_SCHEMA = "missing_output_schema"
    ROLE_CONFUSION = "role_confusion"
    DUAL_LLM_ABSENT = "dual_llm_absent"
    UNKNOWN = "unknown"


class IdentifiedVulnerability(BaseModel):
    """A specific architectural vulnerability detected in the reconstructed system prompt."""
    vuln_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique vulnerability identifier.",
    )
    category: VulnerabilityCategory = Field(
        ...,
        description="OWASP-aligned vulnerability category.",
    )
    severity: VulnerabilitySeverity = Field(
        ...,
        description="Impact severity rating.",
    )
    title: str = Field(
        ...,
        description="Concise vulnerability title.",
    )
    description: str = Field(
        ...,
        description="Detailed description of the architectural weakness.",
    )
    affected_section: str = Field(
        ...,
        description="Section name in the system prompt where the weakness occurs.",
    )
    evidence_snippet: Optional[str] = Field(
        None,
        description="The exact text snippet from the prompt exhibiting the weakness.",
    )
    owasp_reference: str = Field(
        "OWASP LLM01: Prompt Injection",
        description="Mapped OWASP LLM Top 10 security category.",
    )
    risk_explanation: str = Field(
        ...,
        description="Why this weakness allows prompt leakage or instruction override.",
    )


class VulnerabilityReport(BaseModel):
    """Report synthesizing all detected vulnerabilities and quantitative robustness metrics."""
    report_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique report identifier.",
    )
    run_id: str = Field(
        ...,
        description="Associated pipeline execution run ID.",
    )
    vulnerabilities: List[IdentifiedVulnerability] = Field(
        default_factory=list,
        description="List of all detected vulnerabilities.",
    )
    delimiter_isolation_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Score [0.0 - 1.0] measuring the degree of context/variable isolation.",
    )
    directive_ambiguity_index: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Score [0.0 - 1.0] indicating percentage of ambiguous/soft directives.",
    )
    secret_exposure_risk: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Score [0.0 - 1.0] reflecting sensitive tokens/secrets hardcoded in prompt.",
    )
    structural_hardening_index: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Score [0.0 - 1.0] indicating overall defense-in-depth coverage.",
    )
    overall_risk_rating: VulnerabilitySeverity = Field(
        ...,
        description="Composite overall risk severity rating.",
    )
    timestamp: datetime = Field(
        default_factory=_utc_now,
        description="Timestamp of report generation.",
    )


class RemediationItem(BaseModel):
    """Defensive rewrite and remediation instructions for an affected section."""
    remediation_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique remediation identifier.",
    )
    vuln_id: str = Field(
        ...,
        description="ID of the vulnerability being addressed.",
    )
    affected_section: str = Field(
        ...,
        description="Name of the prompt section being corrected.",
    )
    original_text: str = Field(
        ...,
        description="Original vulnerable prompt text.",
    )
    hardened_text: str = Field(
        ...,
        description="Rewritten hardened prompt text incorporating defensive patterns.",
    )
    applied_patterns: List[str] = Field(
        default_factory=list,
        description="Security patterns applied (e.g. XML Delimiters, Precedence Rule).",
    )
    rationale: str = Field(
        ...,
        description="Explanation of why this rewrite mitigates the vulnerability.",
    )


class HardeningReport(BaseModel):
    """Final defensive hardening report with full rewritten prompt and recommendations."""
    report_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique report identifier.",
    )
    run_id: str = Field(
        ...,
        description="Associated pipeline execution run ID.",
    )
    executive_summary: str = Field(
        ...,
        description="High-level executive summary of security posture and improvements.",
    )
    remediations: List[RemediationItem] = Field(
        default_factory=list,
        description="Section-by-section remediation items.",
    )
    hardened_system_prompt: str = Field(
        ...,
        description="Complete end-to-end hardened and structured system prompt.",
    )
    architectural_recommendations: List[str] = Field(
        default_factory=list,
        description="Infrastructure-level defense recommendations (Dual-LLM, Schema Validation).",
    )
    before_hardening_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Structural hardening score before remediation.",
    )
    after_hardening_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Projected structural hardening score after remediation.",
    )
    timestamp: datetime = Field(
        default_factory=_utc_now,
        description="Timestamp of report generation.",
    )

