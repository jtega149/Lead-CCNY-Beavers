"""
verifier.py  — Taamim
Independent purchase verifier.

Checks whether the agent's purchase justification actually matches
the owner's mandate. The agent never approves its own spending.

Branch: taamim/verifier
Route:  POST /verify
"""

from fastapi import APIRouter
from pydantic import BaseModel

from models import CheckResult, Mandate, PurchaseRequest

router = APIRouter(tags=["verifier"])


# ────────────────────────────────────────────────────────────────────
# Core function — this is what John imports
# ────────────────────────────────────────────────────────────────────

def verify_purchase(purchase: PurchaseRequest, mandate: Mandate) -> CheckResult:
    """
    TODO: Implement rules from Product.md:

    1. amount > mandate.max_amount           → block, risk 90
    2. category not in allowed_categories    → block, risk 80
    3. justification doesn't mention task    → flag,  risk 60
    4. otherwise                             → pass,  risk 10

    Optional: call Azure OpenAI if AZURE_OPENAI_KEY is set, fall back to rules.
    """
    # STUB — replace with real logic
    return CheckResult(
        check_name="verifier",
        status="pass",
        risk=0,
        reasons=["stub — not yet implemented"],
    )


# ────────────────────────────────────────────────────────────────────
# Route
# ────────────────────────────────────────────────────────────────────

class _VerifyIn(BaseModel):
    purchase: PurchaseRequest
    mandate: Mandate


@router.post("/verify", response_model=CheckResult)
async def verify_endpoint(body: _VerifyIn):
    """Standalone route: POST /verify with {purchase, mandate}."""
    return verify_purchase(body.purchase, body.mandate)
