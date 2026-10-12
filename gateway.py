"""
gateway.py  — John
Judgment gateway: orchestrates the three checks, applies the routing rule,
requests a receipt, and settles through mock AP4M.

Branch: john/gateway
Routes: POST /judge
        POST /judge/{request_id}/decision   (human approves / rejects a held payment)
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from models import (
    CheckResult,
    DecisionReceipt,
    Mandate,
    PaymentHistoryEntry,
    PurchaseRequest,
    Settlement,
)

from sense_check import check_sensibility

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
    route: str                                  # "auto_approve" | "hold" | "block" | "human_approve"
    checks: list[CheckResult]
    receipt: DecisionReceipt
    settlement: Settlement | None = None
    agent_pay: dict                             # what AP4M's own screen() said, before our layer


class _Held(BaseModel):
    purchase: PurchaseRequest
    mandate: Mandate
    checks: list[CheckResult]
    delivered: bool
    agent_pay: dict


# Payments waiting on a human, keyed by request_id
HELD: dict[str, _Held] = {}


def _as_dict(result) -> dict:
    return result.model_dump() if hasattr(result, "model_dump") else dict(result)


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

    0. Run AP4M's own credential + permission screen (block if it declines)
    1. Call check_provenance, verify_purchase, assess_risk
    2. Apply the routing rule (route_for)
    3. Call build_receipt
    4. If auto_approve → call settle; if hold → park it for a human
    5. Return JudgeResult
    """
    if history is None:
        history = []

    agent_pay = _as_dict(screen(purchase, mandate))

    prov = check_provenance(purchase, mandate)
    ver = verify_purchase(purchase, mandate)
    risk = assess_risk(purchase, history)
    sense = check_sensibility(purchase, mandate)
    checks = [prov, ver, risk, sense]

    route = route_for(checks) if agent_pay.get("permitted", True) else "block"

    receipt = build_receipt(purchase, mandate, checks, route, delivered)
    settlement = settle(purchase.request_id, purchase.amount, route) if route == "auto_approve" else None

    if route == "hold":
        HELD[purchase.request_id] = _Held(
            purchase=purchase, mandate=mandate, checks=checks,
            delivered=delivered, agent_pay=agent_pay,
        )

    return JudgeResult(
        route=route, checks=checks, receipt=receipt,
        settlement=settlement, agent_pay=agent_pay,
    )


def decide(request_id: str, approve: bool) -> JudgeResult:
    """
    Human-in-the-loop for held payments. Approving settles it as "human_approve"
    and issues a new signed receipt; rejecting turns it into a block.
    """
    held = HELD.pop(request_id, None)
    if held is None:
        raise KeyError(request_id)

    route = "human_approve" if approve else "block"
    receipt = build_receipt(held.purchase, held.mandate, held.checks, route, held.delivered)
    settlement = settle(request_id, held.purchase.amount, route) if approve else None

    return JudgeResult(
        route=route, checks=held.checks, receipt=receipt,
        settlement=settlement, agent_pay=held.agent_pay,
    )


# ────────────────────────────────────────────────────────────────────
# Route
# ────────────────────────────────────────────────────────────────────

class _JudgeIn(BaseModel):
    purchase: PurchaseRequest
    mandate: Mandate
    history: list[PaymentHistoryEntry] = []
    delivered: bool = True


@router.post("/judge", response_model=JudgeResult)
def judge_endpoint(body: _JudgeIn):
    """POST /judge — the front door for the Judgment Layer.
    Plain `def` so FastAPI runs it in a worker thread: the Azure sense check is a blocking HTTP call."""
    return judge(body.purchase, body.mandate, body.history, body.delivered)


class _DecisionIn(BaseModel):
    approve: bool


@router.post("/judge/{request_id}/decision", response_model=JudgeResult)
async def decision_endpoint(request_id: str, body: _DecisionIn):
    """POST /judge/{request_id}/decision with {approve: bool} — a person resolves a held payment."""
    try:
        return decide(request_id, body.approve)
    except KeyError:
        raise HTTPException(404, f"No held payment with request_id '{request_id}'.")
