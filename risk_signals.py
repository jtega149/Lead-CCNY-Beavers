"""
risk_signals.py  — Zuzu
Seller reputation, price benchmarking, and pattern detection.

Catches scams that stay inside budget limits: unknown sellers,
wildly overpriced items, and bursts of small payments to one payee.

Branch: zuzu/risk-signals
Route:  POST /risk
"""

from fastapi import APIRouter
from pydantic import BaseModel

from models import CheckResult, PurchaseRequest, PaymentHistoryEntry

router = APIRouter(tags=["risk-signals"])


# ────────────────────────────────────────────────────────────────────
# In-memory seller table (seed data for the demo)
# ────────────────────────────────────────────────────────────────────

SELLERS: dict[str, dict] = {
    # seller_id → { delivery_rate, typical_price_by_category }
    # TODO: populate with 3-4 demo sellers
    # Example:
    # "seller_airline_aa": {"delivery_rate": 0.98, "typical_price": {"travel": 400}},
    # "seller_sketchy":    {"delivery_rate": 0.40, "typical_price": {"software": 30}},
}


# ────────────────────────────────────────────────────────────────────
# Core function — this is what John imports
# ────────────────────────────────────────────────────────────────────

def assess_risk(
    purchase: PurchaseRequest,
    history: list[PaymentHistoryEntry],
) -> CheckResult:
    """
    TODO: Implement rules from Product.md:

    1. Unknown seller                                → flag,  risk 55
    2. amount > 3× typical_price for category        → block, risk 85
       (default typical_price = 50 for unknown sellers)
    3. ≥3 payments in history to same seller_id      → block, risk 80
    4. Known seller, fair price, no repeat pattern   → pass,  risk 15

    Stack reasons, then set status from the worst one.
    """
    # STUB — replace with real logic
    return CheckResult(
        check_name="risk_signals",
        status="pass",
        risk=0,
        reasons=["stub — not yet implemented"],
    )


# ────────────────────────────────────────────────────────────────────
# Route
# ────────────────────────────────────────────────────────────────────

class _RiskIn(BaseModel):
    purchase: PurchaseRequest
    history: list[PaymentHistoryEntry] = []


@router.post("/risk", response_model=CheckResult)
async def risk_endpoint(body: _RiskIn):
    """Standalone route: POST /risk with {purchase, history}."""
    return assess_risk(body.purchase, body.history)
