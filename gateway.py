"""
gateway.py  — John
Judgment gateway: orchestrates the three checks, applies the routing rule,
requests a receipt, and settles through mock AP4M.

Branch: john/gateway
Route:  POST /judge
"""

from fastapi import APIRouter
from pydantic import BaseModel

from models import (
    CheckResult,
    DecisionReceipt,
    Mandate,
    PaymentHistoryEntry,
    PurchaseRequest,
    Settlement,
)

# ── Import the real functions (fall back to stubs if not merged yet) ──

try:
    from provenance import check_provenance
except ImportError:
    def check_provenance(purchase, mandate):
        return CheckResult(check_name="provenance", status="pass", risk=0, reasons=["stub"])

try:
    from verifier import verify_purchase
except ImportError:
    def verify_purchase(purchase, mandate):
        return CheckResult(check_name="verifier", status="pass", risk=0, reasons=["stub"])

try:
    from risk_signals import assess_risk
except ImportError:
    def assess_risk(purchase, history):
        return CheckResult(check_name="risk_signals", status="pass", risk=0, reasons=["stub"])

try:
    from receipts import build_receipt
except ImportError:
    def build_receipt(purchase, mandate, checks, route, delivered=True):
        from models import DecisionReceipt
        return DecisionReceipt(
            request_id=purchase.request_id, mandate=mandate, purchase=purchase,
            checks=checks, route=route, liable_party="none",
            liability_reason="stub", signature="0000",
        )

try:
    from mock_ap4m import screen, settle
except ImportError:
    def screen(purchase, mandate):
        return {"credentialed": True, "permitted": True, "reason": "stub"}
    def settle(request_id, amount, route):
        from models import Settlement
        return Settlement(request_id=request_id, amount=amount, status="refused", note="stub")


router = APIRouter(tags=["gateway"])


# ────────────────────────────────────────────────────────────────────
# Core function
# ────────────────────────────────────────────────────────────────────

class JudgeResult(BaseModel):
    route: str
    checks: list[CheckResult]
    receipt: DecisionReceipt
    settlement: Settlement | None = None


def route_for(checks: list[CheckResult]) -> str:
    """
    Routing rule from Product.md, applied to the highest risk among the checks:
      - any block OR risk >= 70          → block
      - any flag OR risk 40-69, no block → hold
      - all pass AND highest risk < 40   → auto_approve
    """
    statuses = {c.status for c in checks}
    highest = max((c.risk for c in checks), default=0)

    if "block" in statuses or highest >= 70:
        return "block"
    if "flag" in statuses or highest >= 40:
        return "hold"
    return "auto_approve"


def judge(
    purchase: PurchaseRequest,
    mandate: Mandate,
    history: list[PaymentHistoryEntry] | None = None,
    delivered: bool = True,
) -> JudgeResult:
    """
    Full orchestration from Product.md:

    1. Call check_provenance, verify_purchase, assess_risk
    2. Apply the routing rule (route_for)
    3. Call build_receipt
    4. If auto_approve → call settle; otherwise settlement = None
    5. Return JudgeResult
    """
    if history is None:
        history = []

    prov = check_provenance(purchase, mandate)
    ver = verify_purchase(purchase, mandate)
    risk = assess_risk(purchase, history)
    checks = [prov, ver, risk]

    route = route_for(checks)

    receipt = build_receipt(purchase, mandate, checks, route, delivered)
    settlement = settle(purchase.request_id, purchase.amount, route) if route == "auto_approve" else None

    return JudgeResult(route=route, checks=checks, receipt=receipt, settlement=settlement)


# ────────────────────────────────────────────────────────────────────
# Route
# ────────────────────────────────────────────────────────────────────

class _JudgeIn(BaseModel):
    purchase: PurchaseRequest
    mandate: Mandate
    history: list[PaymentHistoryEntry] = []
    delivered: bool = True


@router.post("/judge", response_model=JudgeResult)
async def judge_endpoint(body: _JudgeIn):
    """POST /judge — the front door for the Judgment Layer."""
    return judge(body.purchase, body.mandate, body.history, body.delivered)
