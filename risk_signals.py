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
    "seller_airline_aa": {"delivery_rate": 0.98, "typical_price": {"travel": 400.0}},
    "seller_trusted_software": {"delivery_rate": 0.95, "typical_price": {"software": 50.0}},
    "seller_shady_invoice": {"delivery_rate": 0.20, "typical_price": {"travel": 50.0}},
}


# ────────────────────────────────────────────────────────────────────
# Core function — this is what John imports
# ────────────────────────────────────────────────────────────────────

def assess_risk(
    purchase: PurchaseRequest,
    history: list[PaymentHistoryEntry] | None = None,
) -> CheckResult:
    """
    Assess seller reputation, price benchmarking, and pattern detection.

    Rules from Product.md:
    1. Unknown seller                                → flag,  risk 55
       (default typical_price = 50.0 for unknown sellers)
    2. amount > 3x typical_price for category        → block, risk 85
    3. >= 3 payments in history to same seller_id    → block, risk 80
    4. Known seller, fair price, no repeat pattern   → pass,  risk 15

    Accumulate all applicable reasons, and select worst status and highest risk.
    """
    if history is None:
        history = []

    reasons: list[str] = []
    risks: list[int] = []
    statuses: list[str] = []

    # 1. Unknown seller check
    if purchase.seller_id not in SELLERS:
        reasons.append(f"Unknown seller '{purchase.seller_id}'.")
        statuses.append("flag")
        risks.append(55)
        typical_price = 50.0
    else:
        seller_data = SELLERS[purchase.seller_id]
        category_prices = seller_data.get("typical_price", {})
        if isinstance(category_prices, dict):
            typical_price = float(category_prices.get(purchase.category, 50.0))
        elif isinstance(category_prices, (int, float)):
            typical_price = float(category_prices)
        else:
            typical_price = 50.0

    # 2. Price benchmarking check
    if purchase.amount > 3 * typical_price:
        reasons.append(
            f"Amount ${purchase.amount:.2f} is more than 3x the typical price (${typical_price:.2f}) for category '{purchase.category}'."
        )
        statuses.append("block")
        risks.append(85)

    # 3. Repeated payments to same payee pattern check
    repeat_count = sum(1 for entry in history if entry.seller_id == purchase.seller_id)
    if repeat_count >= 3:
        reasons.append(
            f"Repeated payments (>=3) to payee '{purchase.seller_id}', possible limit-dodging."
        )
        statuses.append("block")
        risks.append(80)

    # 4. Clean path (known seller, normal pricing, normal payment pattern)
    if not reasons:
        reasons.append("Known seller with normal pricing and payment pattern.")
        statuses.append("pass")
        risks.append(15)

    max_risk = max(risks)
    if "block" in statuses or max_risk >= 70:
        final_status = "block"
    elif "flag" in statuses or max_risk >= 40:
        final_status = "flag"
    else:
        final_status = "pass"

    return CheckResult(
        check_name="risk_signals",
        status=final_status,
        risk=max_risk,
        reasons=reasons,
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
