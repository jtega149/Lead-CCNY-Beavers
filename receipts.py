"""
receipts.py  — Axyl
Decision receipts and liability assignment.

Builds a cryptographically signed bundle recording who decided what,
and names who would bear the loss if something goes wrong.

Branch: axyl/receipts
Route:  POST /receipts
"""

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
    TODO: Implement from Product.md:

    Signature:
      HMAC-SHA256 over JSON of all fields except `signature`,
      using DEMO_SECRET.

    Liability (first match wins):
      1. delivered=False and route=auto_approve       → seller
      2. any check is block and route=auto_approve    → verifier
      3. route is block or hold                       → none
      4. mandate.max_amount > 10000 and all passed    → owner
      5. otherwise: agent_developer if any reason
         mentions "untrusted", else none

    For the happy path demo, delivered=True + normal mandate
    should produce liable_party="none".
    """
    # STUB — replace with real logic
    return DecisionReceipt(
        request_id=purchase.request_id,
        mandate=mandate,
        purchase=purchase,
        checks=checks,
        route=route,
        liable_party="none",
        liability_reason="stub — not yet implemented",
        signature="0000",
    )


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
