"""
receipts.py  — Axyl
Decision receipts and liability assignment.

Builds a cryptographically signed bundle recording who decided what,
and names who would bear the loss if something goes wrong.

Branch: axyl/receipts
Route:  POST /receipts
"""

import hashlib
import hmac
import json

from fastapi import APIRouter
from pydantic import BaseModel

from models import (
    CheckResult,
    DecisionReceipt,
    Mandate,
    PurchaseRequest,
)

router = APIRouter(tags=["receipts"])

DEMO_SECRET = "hackathon-demo-secret"


# ────────────────────────────────────────────────────────────────────
# Core function — this is what John imports
# ────────────────────────────────────────────────────────────────────

def build_receipt(
    purchase: PurchaseRequest,
    mandate: Mandate,
    checks: list[CheckResult],
    route: str,
    delivered: bool = True,
) -> DecisionReceipt:
    """
    Builds a signed DecisionReceipt (Product.md).

    Signature:
      HMAC-SHA256 over canonical JSON of all fields except `signature`,
      using DEMO_SECRET.

    Liability (first match wins):
      1. delivered=False and route=auto_approve       → seller
      2. any check is block and route=auto_approve    → verifier
      3. route is block or hold                       → none
      4. mandate.max_amount > 10000 and all passed    → owner
      5. otherwise: agent_developer if any reason
         mentions "untrusted", else none
    """
    liable_party, liability_reason = assign_liability(mandate, checks, route, delivered)

    receipt = DecisionReceipt(
        request_id=purchase.request_id,
        mandate=mandate,
        purchase=purchase,
        checks=checks,
        route=route,
        liable_party=liable_party,
        liability_reason=liability_reason,
        signature="",
    )
    receipt.signature = sign_receipt(receipt)
    return receipt


def assign_liability(
    mandate: Mandate,
    checks: list[CheckResult],
    route: str,
    delivered: bool,
) -> tuple[str, str]:
    """Liability matrix — first match wins."""
    if not delivered and route == "auto_approve":
        return "seller", "Paid and not delivered."
    if route == "auto_approve" and any(c.status == "block" for c in checks):
        return "verifier", "Checker approved a bad purchase."
    if route == "block":
        return "none", "Money did not move."
    if route == "hold":
        return "none", "Waiting on a person."
    if mandate.max_amount > 10000 and all(c.status == "pass" for c in checks):
        return "owner", "Mandate is broad enough to allow a very large payment."
    if any("untrusted" in r.lower() for c in checks for r in c.reasons):
        return "agent_developer", "Agent acted on an instruction from untrusted content."
    return "none", "Checks passed, no fault assigned."


def sign_receipt(receipt: DecisionReceipt) -> str:
    """HMAC-SHA256 hex over the canonical JSON of every field except `signature`."""
    payload = json.dumps(
        receipt.model_dump(exclude={"signature"}),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hmac.new(DEMO_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()


def verify_receipt(receipt: DecisionReceipt) -> bool:
    """True if the receipt's signature matches its contents (i.e. not tampered)."""
    return hmac.compare_digest(receipt.signature, sign_receipt(receipt))


# ────────────────────────────────────────────────────────────────────
# Route
# ────────────────────────────────────────────────────────────────────

class _ReceiptIn(BaseModel):
    purchase: PurchaseRequest
    mandate: Mandate
    checks: list[CheckResult]
    route: str
    delivered: bool = True


@router.post("/receipts", response_model=DecisionReceipt)
async def receipt_endpoint(body: _ReceiptIn):
    """Standalone route: POST /receipts."""
    return build_receipt(
        body.purchase, body.mandate, body.checks, body.route, body.delivered,
    )
