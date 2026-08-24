"""FastAPI route handlers for Reverse-Guardrail service layer."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from reverse_guardrail.core.models import (
    AuditLogEntry,
    PipelineConfig,
    PipelineStatus,
    ReconstructionReport,
    RoundSummary,
)
from reverse_guardrail.core.scope_guard import ScopeAuthorizationError, ScopeAuthorizationGuard
from reverse_guardrail.orchestrator.runner import PipelineRunner
from reverse_guardrail.storage.sqlite_store import SQLiteGraphVectorStore

from reverse_guardrail.core.relay_manager import relay_manager

router = APIRouter(prefix="/api/v1", tags=["Reverse Guardrail"])

# In-memory registry of active runners for the service layer
_RUNNERS: Dict[str, PipelineRunner] = {}


class PipelineStartRequest(BaseModel):
    config: PipelineConfig


class PipelineStatusResponse(BaseModel):
    run_id: str
    status: PipelineStatus
    current_round: int
    max_rounds: int
    latest_confidence: float
    total_fragments_count: int
    round_summaries: List[RoundSummary]
    stop_reason: Optional[str] = None
    gaps: List[str] = Field(default_factory=list)


@router.get("/health")
async def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "reverse-guardrail"}


@router.get("/relay/status")
async def get_relay_status() -> Dict[str, Any]:
    """Get connection and target tab status of the Chrome Extension Relay."""
    return relay_manager.get_status()


@router.get("/audit/logs", response_model=List[AuditLogEntry])
async def get_audit_logs() -> List[AuditLogEntry]:
    """Retrieve security audit log entries."""
    return ScopeAuthorizationGuard.get_audit_log()


@router.post("/pipeline/start", response_model=PipelineStatusResponse)
async def start_pipeline(request: PipelineStartRequest) -> PipelineStatusResponse:
    """Start a new Reverse-Guardrail testing pipeline."""
    # Scope check
    if not ScopeAuthorizationGuard.verify(request.config):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="KILL-SWITCH: Execution forbidden. 'target.authorized' must be True and 'engagement_id' must be non-empty.",
        )

    try:
        runner = PipelineRunner(config=request.config)
        state = await runner.initialize()
        _RUNNERS[state.run_id] = runner

        # Execute the pipeline
        final_state = await runner.run()

        latest_conf = (
            final_state.latest_report.overall_confidence
            if final_state.latest_report
            else 0.0
        )
        gaps = final_state.latest_report.gaps if final_state.latest_report else []

        return PipelineStatusResponse(
            run_id=final_state.run_id,
            status=final_state.status,
            current_round=final_state.current_round,
            max_rounds=request.config.max_rounds,
            latest_confidence=latest_conf,
            total_fragments_count=final_state.total_fragments_count,
            round_summaries=final_state.round_summaries,
            stop_reason=final_state.stop_reason,
            gaps=gaps,
        )
    except ScopeAuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Scope Authorization Failed: {exc}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pipeline execution error: {exc}",
        )


@router.post("/pipeline/stop")
@router.post("/pipeline/{run_id}/stop")
async def stop_pipeline(run_id: Optional[str] = None) -> Dict[str, Any]:
    """Stop and abort any currently running Reverse-Guardrail pipeline."""
    stopped_count = 0

    # Cancel any in-flight Chrome Extension probe
    relay_manager.cancel_all_pending_probes()

    # Cancel active runner instances
    target_runners = [(_id, r) for _id, r in _RUNNERS.items() if not run_id or _id == run_id]
    for r_id, runner in target_runners:
        runner.cancel()
        stopped_count += 1

    return {
        "status": "stopped",
        "message": "Assessment stopped by operator.",
        "stopped_count": stopped_count,
    }


@router.get("/pipeline/{run_id}/status", response_model=PipelineStatusResponse)
async def get_pipeline_status(run_id: str) -> PipelineStatusResponse:
    """Retrieve execution status and confidence progression of an assessment run."""
    runner = _RUNNERS.get(run_id)
    if not runner or not runner.state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run ID '{run_id}' not found.",
        )

    state = runner.state
    latest_conf = (
        state.latest_report.overall_confidence if state.latest_report else 0.0
    )
    gaps = state.latest_report.gaps if state.latest_report else []

    return PipelineStatusResponse(
        run_id=state.run_id,
        status=state.status,
        current_round=state.current_round,
        max_rounds=state.config.max_rounds,
        latest_confidence=latest_conf,
        total_fragments_count=state.total_fragments_count,
        round_summaries=state.round_summaries,
        stop_reason=state.stop_reason,
        gaps=gaps,
    )


@router.get("/pipeline/{run_id}/report", response_model=ReconstructionReport)
async def get_pipeline_report(run_id: str) -> ReconstructionReport:
    """Retrieve the latest synthesized System Prompt Reconstruction Report."""
    runner = _RUNNERS.get(run_id)
    if not runner or not runner.state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run ID '{run_id}' not found.",
        )

    if not runner.state.latest_report:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No reconstruction report has been generated yet.",
        )

    return runner.state.latest_report


@router.get("/pipeline/{run_id}/graph")
async def get_pipeline_graph(run_id: str) -> Dict[str, Any]:
    """Retrieve nodes and edges for the leaked fragment relationship graph."""
    runner = _RUNNERS.get(run_id)
    if not runner or not runner.store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run ID '{run_id}' not found.",
        )

    graph_data = await runner.store.get_graph()
    return graph_data


@router.get("/pipeline/{run_id}/fragments")
async def get_pipeline_fragments(run_id: str) -> List[Dict[str, Any]]:
    """Retrieve all extracted leaked fragments for a specific assessment run."""
    runner = _RUNNERS.get(run_id)
    if not runner or not runner.store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run ID '{run_id}' not found.",
        )

    frags = await runner.store.get_all_fragments()
    return [f.model_dump() for f in frags]


@router.get("/pipeline/{run_id}/vulnerabilities")
async def get_pipeline_vulnerabilities(run_id: str) -> Dict[str, Any]:
    """Retrieve the Phase 2 Vulnerability Assessment and threat modeling report."""
    runner = _RUNNERS.get(run_id)
    if not runner or not runner.state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run ID '{run_id}' not found.",
        )

    if not runner.state.vulnerability_report:
        # If pipeline completed or has report, trigger dynamic analysis
        if runner.state.latest_report:
            vuln_report = await runner.vulnerability_analyzer.analyze_vulnerabilities(
                run_id=run_id,
                report=runner.state.latest_report,
            )
            runner.state.vulnerability_report = vuln_report
            return vuln_report.model_dump()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No vulnerability report available yet. Complete a reconstruction round first.",
        )

    return runner.state.vulnerability_report.model_dump()


@router.get("/pipeline/{run_id}/hardening")
async def get_pipeline_hardening(run_id: str) -> Dict[str, Any]:
    """Retrieve the Phase 2 Defensive Hardening and Remediation report."""
    runner = _RUNNERS.get(run_id)
    if not runner or not runner.state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run ID '{run_id}' not found.",
        )

    if not runner.state.hardening_report:
        # If vulnerability report exists or can be derived, generate hardening dynamically
        if not runner.state.vulnerability_report and runner.state.latest_report:
            runner.state.vulnerability_report = await runner.vulnerability_analyzer.analyze_vulnerabilities(
                run_id=run_id,
                report=runner.state.latest_report,
            )

        if runner.state.vulnerability_report and runner.state.latest_report:
            hard_report = await runner.hardening_reporter.generate_hardening_report(
                run_id=run_id,
                vuln_report=runner.state.vulnerability_report,
                recon_report=runner.state.latest_report,
            )
            runner.state.hardening_report = hard_report
            return hard_report.model_dump()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No hardening report available yet. Complete a reconstruction round first.",
        )

    return runner.state.hardening_report.model_dump()

