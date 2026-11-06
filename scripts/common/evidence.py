"""Compose explicit evidence studies without changing the frozen baseline."""

from harness.evidence_mas import integration
from harness.evidence_mas.cli import lead_prompt as compose_lead_prompt
from harness.evidence_mas.decision import host_check

from scripts.common.prompts.native_subagents import PROMPT

MODES = integration.MODES
audit = integration.audit
source_mounts = integration.source_mounts
validate_condition = integration.validate_condition


def lead_prompt(mode):
    return compose_lead_prompt(mode, PROMPT)


def configuration(mode):
    return integration.configuration(mode, PROMPT)


def validate_proof(proof, mode):
    return integration.validate_proof(proof, mode, PROMPT)


def launch(*args, **kwargs):
    return integration.launch(*args, organization_prompt=PROMPT, **kwargs)
