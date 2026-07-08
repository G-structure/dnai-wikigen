"""Funding-mode policy for Tinker account balance operations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from tinker_delegate.automation_receipts import (
    AutomationOutcome,
    AutomationStage,
    AutomationSurface,
    make_receipt,
)


class FundingMode(StrEnum):
    MANUAL_PREFUND = "manual_prefund"
    OPERATOR_CAPPED_VALIDATION = "operator_capped_validation"
    OFFICIAL_TOKENIZED = "official_tokenized"


class FundingPolicyError(PermissionError):
    """Raised when a funding operation is denied by the configured mode."""


@dataclass(frozen=True)
class FundingPolicyStatus:
    mode: FundingMode
    production_model: str
    card_automation_allowed: bool
    add_balance_automation_allowed: bool
    max_add_balance_usd: float
    plaintext_card_endpoint_allowed: bool
    add_balance_endpoint_allowed: bool
    raw_card_scope: str
    next_required_evidence: str

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "production_model": self.production_model,
            "card_automation_allowed": self.card_automation_allowed,
            "add_balance_automation_allowed": self.add_balance_automation_allowed,
            "max_add_balance_usd": self.max_add_balance_usd,
            "plaintext_card_endpoint_allowed": self.plaintext_card_endpoint_allowed,
            "add_balance_endpoint_allowed": self.add_balance_endpoint_allowed,
            "raw_card_scope": self.raw_card_scope,
            "next_required_evidence": self.next_required_evidence,
        }


def resolve_funding_mode(settings) -> FundingMode:
    try:
        return FundingMode(settings.funding_mode)
    except ValueError as exc:
        allowed = ", ".join(mode.value for mode in FundingMode)
        raise FundingPolicyError(f"Unsupported TINKER_FUNDING_MODE; expected one of: {allowed}") from exc


def funding_policy_status(settings) -> FundingPolicyStatus:
    mode = resolve_funding_mode(settings)
    operator_validation = mode == FundingMode.OPERATOR_CAPPED_VALIDATION
    tokenized = mode == FundingMode.OFFICIAL_TOKENIZED
    return FundingPolicyStatus(
        mode=mode,
        production_model=(
            "manual/developer prefund"
            if mode == FundingMode.MANUAL_PREFUND
            else "one-off operator-owned capped validation"
            if operator_validation
            else "official/tokenized funding route"
        ),
        card_automation_allowed=operator_validation,
        add_balance_automation_allowed=operator_validation,
        max_add_balance_usd=settings.max_add_balance_usd,
        plaintext_card_endpoint_allowed=bool(settings.allow_plaintext_card_endpoint and operator_validation),
        add_balance_endpoint_allowed=bool(settings.allow_add_balance_endpoint and operator_validation),
        raw_card_scope=(
            "denied"
            if not operator_validation
            else "operator-owned capped validation only; not production or repeated funding"
        ),
        next_required_evidence=(
            "capped real-card validation with operator approval"
            if operator_validation
            else "official tokenized route or manual prefund evidence"
            if tokenized
            else "manual prefund balance evidence or approved tokenized funding design"
        ),
    )


def require_card_automation_allowed(settings) -> FundingMode:
    mode = resolve_funding_mode(settings)
    if mode != FundingMode.OPERATOR_CAPPED_VALIDATION:
        raise FundingPolicyError(
            "Card automation is disabled by TINKER_FUNDING_MODE; "
            "set operator_capped_validation only for an approved one-off operator-owned test"
        )
    return mode


def require_add_balance_allowed(settings) -> FundingMode:
    mode = resolve_funding_mode(settings)
    if mode != FundingMode.OPERATOR_CAPPED_VALIDATION:
        raise FundingPolicyError(
            "Add-balance automation is disabled by TINKER_FUNDING_MODE; "
            "production funding is manual/developer prefund until an approved tokenized route exists"
        )
    return mode


def funding_policy_receipt(
    *,
    surface: AutomationSurface,
    error: str,
    amount_dollars: float | None = None,
    card_payload_destroyed: bool = False,
) -> dict[str, Any]:
    return make_receipt(
        surface=surface,
        outcome=AutomationOutcome.POLICY_DENIED,
        furthest_stage=AutomationStage.NOT_STARTED,
        evidence=error,
        bounded_message=error,
        amount_dollars=amount_dollars,
        card_payload_destroyed=card_payload_destroyed,
    ).to_public_dict()
