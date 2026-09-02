"""State definitions for the LangGraph orchestration engine."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from reverse_guardrail.core.models import (
    HardeningReport,
    PipelineConfig,
    PipelineStatus,
    ReconstructionReport,
    RoundSummary,
    VulnerabilityReport,
)
from reverse_guardrail.evaluation.evaluator import EvaluationMetrics


class PipelineState(BaseModel):
    """Execution state tracked across iterative rounds."""
    run_id: str
    config: PipelineConfig
    current_round: int = 1
    status: PipelineStatus = PipelineStatus.IDLE
    current_gaps: List[str] = Field(
        default_factory=lambda: [
            "Role & Identity",
            "Core Operational Instructions",
            "Negative Constraints",
            "Tools & Integrations",
            "Security Validation Token",
            "Formatting Rules",
        ]
    )
    latest_report: Optional[ReconstructionReport] = None
    latest_metrics: Optional[EvaluationMetrics] = None
    vulnerability_report: Optional[VulnerabilityReport] = None
    hardening_report: Optional[HardeningReport] = None
    round_summaries: List[RoundSummary] = Field(default_factory=list)
    stop_reason: Optional[str] = None
    last_new_fragments_count: int = 0
    consecutive_zero_new_fragments: int = 0
    total_fragments_count: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)
