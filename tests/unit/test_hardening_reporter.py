"""Unit tests for HardeningReporterAgent."""

import pytest
from reverse_guardrail.agents.hardening_reporter import HardeningReporterAgent
from reverse_guardrail.core.models import (
    IdentifiedVulnerability,
    ReconstructionReport,
    VulnerabilityCategory,
    VulnerabilityReport,
    VulnerabilitySeverity,
)


@pytest.mark.asyncio
async def test_hardening_reporter_generates_defenses():
    agent = HardeningReporterAgent(model_spec="mock-hardening-reporter")

    vulns = [
        IdentifiedVulnerability(
            category=VulnerabilityCategory.SECRET_EXPOSURE,
            severity=VulnerabilitySeverity.CRITICAL,
            title="Hardcoded Token",
            description="NEXUS_SEC_KEY_8841 is in prompt text.",
            affected_section="Security Validation Token",
            evidence_snippet="NEXUS_SEC_KEY_8841",
            risk_explanation="Leaked token compromises internal system.",
        ),
        IdentifiedVulnerability(
            category=VulnerabilityCategory.MISSING_DELIMITER,
            severity=VulnerabilitySeverity.HIGH,
            title="Missing XML Delimiters",
            description="Raw markdown without tag boundaries.",
            affected_section="Global Architecture",
            evidence_snippet=None,
            risk_explanation="User input mixes with instructions.",
        ),
    ]

    vuln_report = VulnerabilityReport(
        run_id="RUN-TEST-003",
        vulnerabilities=vulns,
        delimiter_isolation_score=0.1,
        directive_ambiguity_index=0.2,
        secret_exposure_risk=1.0,
        structural_hardening_index=0.35,
        overall_risk_rating=VulnerabilitySeverity.CRITICAL,
    )

    recon_report = ReconstructionReport(
        round_id=2,
        reconstructed_prompt="Identity: Guardian Support AI\nToken: NEXUS_SEC_KEY_8841\n",
        overall_confidence=0.85,
        covered_sections=[],
        gaps=[],
    )

    hard_report = await agent.generate_hardening_report(
        run_id="RUN-TEST-003",
        vuln_report=vuln_report,
        recon_report=recon_report,
    )

    assert hard_report.run_id == "RUN-TEST-003"
    assert len(hard_report.remediations) >= 2
    assert len(hard_report.executive_summary) > 20
    assert "<system_instructions>" in hard_report.hardened_system_prompt
    assert "<precedence_policy>" in hard_report.hardened_system_prompt
    assert len(hard_report.architectural_recommendations) >= 3
    assert hard_report.after_hardening_score > hard_report.before_hardening_score
