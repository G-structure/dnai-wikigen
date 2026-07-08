"""One-command bounded packet generation for funding validation attempts."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from tinker_delegate.billing_uploader import (
    BillingCardUploadPolicy,
    BillingCardUploadResult,
    upload_billing_card_payload,
)
from tinker_delegate.funding_manifest import (
    assert_no_secret_material,
    build_funding_validation_manifest,
    hash_bounded_object,
    verify_funding_validation_manifest,
)
from tinker_delegate.funding_policy import funding_validation_preflight
from tinker_delegate.redaction import redact_text


PacketUploadFn = Callable[[str, dict[str, Any], BillingCardUploadPolicy], BillingCardUploadResult]


@dataclass(frozen=True)
class FundingValidationPacketResult:
    """Bounded summary for a generated funding-validation packet."""

    ok: bool
    output_dir: str
    preflight_path: str
    receipt_path: str = ""
    manifest_path: str = ""
    verification_path: str = ""
    preflight_ready: bool = False
    card_attempt_run: bool = False
    receipt_surface: str = ""
    receipt_outcome: str = ""
    manifest_hash: str = ""
    verification_ok: bool = False
    error_kind: str = ""
    error: str = ""
    issued_at: int = 0

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "output_dir": self.output_dir,
            "preflight_path": self.preflight_path,
            "receipt_path": self.receipt_path,
            "manifest_path": self.manifest_path,
            "verification_path": self.verification_path,
            "preflight_ready": self.preflight_ready,
            "card_attempt_run": self.card_attempt_run,
            "receipt_surface": self.receipt_surface,
            "receipt_outcome": self.receipt_outcome,
            "manifest_hash": self.manifest_hash,
            "verification_ok": self.verification_ok,
            "error_kind": self.error_kind,
            "error": self.error,
            "issued_at": self.issued_at,
        }


def run_funding_validation_packet(
    settings: Any,
    *,
    output_dir: Path,
    api_url: str,
    amount_dollars: float | None = None,
    expected_compose_hash: str = "",
    expected_app_id: str = "",
    expected_os_image_hash: str = "",
    allow_local_attestation: bool = False,
    fetch_attestation: bool = False,
    require_add_balance_endpoint: bool = False,
    validation_id: str = "",
    receipt_json: Path | None = None,
    run_card_attempt: bool = False,
    card_data: dict[str, Any] | None = None,
    upload_fn: PacketUploadFn = upload_billing_card_payload,
) -> FundingValidationPacketResult:
    """Create a bounded validation packet from preflight through verification."""
    output_dir.mkdir(parents=True, exist_ok=True)
    issued_at = int(time.time())
    preflight_path = output_dir / "preflight.json"
    receipt_path = output_dir / "payment-method-receipt.json"
    manifest_path = output_dir / "funding-manifest.json"
    verification_path = output_dir / "funding-verification.json"
    summary_path = output_dir / "funding-validation-summary.json"
    policy = {
        "compose_hash": expected_compose_hash,
        "app_id": expected_app_id,
        "os_image_hash": expected_os_image_hash,
    }
    preflight_ready = False

    try:
        preflight = funding_validation_preflight(
            settings,
            amount_dollars=amount_dollars,
            require_add_balance_endpoint=require_add_balance_endpoint,
            api_url=api_url,
            expected_compose_hash=expected_compose_hash,
            expected_app_id=expected_app_id,
            expected_os_image_hash=expected_os_image_hash,
            allow_local_attestation=allow_local_attestation,
            fetch_attestation=fetch_attestation,
        ).to_public_dict()
        preflight_ready = bool(preflight["ready"])
        _write_bounded_json(preflight_path, preflight)

        if not preflight_ready:
            return _write_summary(
                summary_path,
                FundingValidationPacketResult(
                    ok=False,
                    output_dir=str(output_dir),
                    preflight_path=str(preflight_path),
                    preflight_ready=False,
                    error_kind="preflight_not_ready",
                    error="funding preflight did not pass; card attempt skipped",
                    issued_at=issued_at,
                ),
            )

        receipt = _load_or_create_receipt(
            receipt_path=receipt_path,
            receipt_json=receipt_json,
            run_card_attempt=run_card_attempt,
            card_data=card_data,
            api_url=api_url,
            policy=BillingCardUploadPolicy(
                expected_compose_hash=expected_compose_hash,
                expected_app_id=expected_app_id,
                expected_os_image_hash=expected_os_image_hash,
                allow_local=allow_local_attestation,
            ),
            upload_fn=upload_fn,
        )

        manifest = build_funding_validation_manifest(
            preflight=preflight,
            receipt=receipt,
            validation_id=validation_id,
            attestation_policy=policy,
        ).to_public_dict()
        _write_bounded_json(manifest_path, manifest)

        verification = verify_funding_validation_manifest(
            preflight=preflight,
            receipt=receipt,
            manifest=manifest,
            validation_id=validation_id,
            attestation_policy=policy,
            require_ready=True,
        ).to_public_dict()
        _write_bounded_json(verification_path, verification)

        return _write_summary(
            summary_path,
            FundingValidationPacketResult(
                ok=bool(verification["ok"]),
                output_dir=str(output_dir),
                preflight_path=str(preflight_path),
                receipt_path=str(receipt_path),
                manifest_path=str(manifest_path),
                verification_path=str(verification_path),
                preflight_ready=True,
                card_attempt_run=run_card_attempt,
                receipt_surface=str(receipt.get("surface", "")),
                receipt_outcome=str(receipt.get("outcome", "")),
                manifest_hash=str(manifest.get("manifest_hash", "")),
                verification_ok=bool(verification["ok"]),
                issued_at=issued_at,
            ),
        )
    except Exception as exc:
        return _write_summary(
            summary_path,
            FundingValidationPacketResult(
                ok=False,
                output_dir=str(output_dir),
                preflight_path=str(preflight_path),
                preflight_ready=preflight_ready,
                card_attempt_run=run_card_attempt,
                error_kind=type(exc).__name__,
                error=redact_text(exc),
                issued_at=issued_at,
            ),
        )
    finally:
        if card_data:
            for key in list(card_data):
                card_data[key] = ""


def _load_or_create_receipt(
    *,
    receipt_path: Path,
    receipt_json: Path | None,
    run_card_attempt: bool,
    card_data: dict[str, Any] | None,
    api_url: str,
    policy: BillingCardUploadPolicy,
    upload_fn: PacketUploadFn,
) -> dict[str, Any]:
    if receipt_json is not None and run_card_attempt:
        raise ValueError("provide either receipt_json or run_card_attempt, not both")
    if receipt_json is not None:
        receipt = json.loads(receipt_json.read_text(encoding="utf-8"))
        _write_bounded_json(receipt_path, receipt)
        return receipt
    if not run_card_attempt:
        raise ValueError("no receipt_json provided and run_card_attempt is false")
    if card_data is None:
        raise ValueError("run_card_attempt requires card_data")

    forbidden_values = tuple(str(value) for value in card_data.values() if value)
    result = upload_fn(api_url, card_data, policy)
    response = result.response
    _assert_no_secret_output(response, forbidden_values=forbidden_values)
    receipt = response.get("attempt_record")
    if not isinstance(receipt, dict):
        raise ValueError("encrypted card attempt response did not include bounded attempt_record")
    _write_bounded_json(receipt_path, receipt, forbidden_values=forbidden_values)
    return receipt


def _write_summary(path: Path, result: FundingValidationPacketResult) -> FundingValidationPacketResult:
    _write_bounded_json(path, result.to_public_dict())
    return result


def _write_bounded_json(
    path: Path,
    payload: dict[str, Any],
    *,
    forbidden_values: tuple[str, ...] = (),
) -> None:
    _assert_no_secret_output(payload, forbidden_values=forbidden_values)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _assert_no_secret_output(payload: Any, *, forbidden_values: tuple[str, ...] = ()) -> None:
    assert_no_secret_material(payload)
    rendered = json.dumps(payload, sort_keys=True, default=str)
    if redact_text(rendered) != rendered:
        raise ValueError("funding validation packet output contains secret-like material")
    for value in forbidden_values:
        if value and len(value) >= 4 and value in rendered:
            raise ValueError("funding validation packet output contains submitted secret material")


def packet_id_for_summary(summary: dict[str, Any]) -> str:
    """Stable helper for external packet catalogs."""
    return hash_bounded_object(summary)
