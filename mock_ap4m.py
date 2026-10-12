"""
mock_ap4m.py  — Kelvin
Mock of Mastercard Agent Pay for Machines (AP4M).

Pretends to credential an agent, check a budget, move money, and settle.
Our layer (the judgment product) sits in front of this mock.

Branch: kelvin/mock-ap4m
Routes: POST /ap4m/screen, POST /ap4m/settle, GET /ap4m/settlements/{request_id}
"""

from fastapi import APIRouter
from pydantic import BaseModel

from models import Mandate, PurchaseRequest, Settlement

router = APIRouter(prefix="/ap4m", tags=["mock-ap4m"])

# In-memory settlement store (stand-in for guaranteed settlement ledger)
settlements: dict[str, Settlement] = {}


# ────────────────────────────────────────────────────────────────────
# Screen — pretend credentialing + permissioning
# ────────────────────────────────────────────────────────────────────

class _ScreenIn(BaseModel):
    purchase: PurchaseRequest
    mandate: Mandate


class ScreenResult(BaseModel):
    credentialed: bool
    permitted: bool
    reason: str = ""


def screen(purchase: PurchaseRequest, mandate: Mandate) -> ScreenResult:
    """
    TODO: Implement from Product.md:

    - agent_id must start with "agent_"  → otherwise refuse (credential check)
    - amount <= mandate.max_amount AND category in allowed_categories
      → otherwise refuse (permissioning)
    - Return { credentialed, permitted } or a short reason.
    """
    # STUB
    return ScreenResult(credentialed=True, permitted=True)


@router.post("/screen", response_model=ScreenResult)
async def screen_endpoint(body: _ScreenIn):
    return screen(body.purchase, body.mandate)


# ────────────────────────────────────────────────────────────────────
# Settle — called only after gateway says auto_approve
# ────────────────────────────────────────────────────────────────────

class _SettleIn(BaseModel):
    request_id: str
    amount: float
    route: str  # the gateway's routing decision


def settle(request_id: str, amount: float, route: str) -> Settlement:
    """
    TODO: Implement from Product.md:

    - If route != "auto_approve" → status "refused"
    - amount >= 100              → status "escrow"
    - amount < 100               → status "clawback_window"

    Store in settlements dict keyed by request_id.
    """
    # STUB
    s = Settlement(request_id=request_id, amount=amount, status="refused", note="stub")
    settlements[request_id] = s
    return s


@router.post("/settle", response_model=Settlement)
async def settle_endpoint(body: _SettleIn):
    return settle(body.request_id, body.amount, body.route)


@router.get("/settlements/{request_id}", response_model=Settlement)
async def get_settlement(request_id: str):
    if request_id not in settlements:
        from fastapi import HTTPException
        raise HTTPException(404, "Settlement not found")
    return settlements[request_id]
