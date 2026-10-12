"""
mock_ap4m.py  — Kelvin
Mock of Mastercard Agent Pay for Machines (AP4M).

Pretends to credential an agent, check a budget, move money, and settle.
Also includes MDES Agentic Token enrollment and simulated card network authorization.
Our layer (the judgment product) sits in front of this mock.

Branch: kelvin/mock-ap4m
Routes:
  - POST /ap4m/screen
  - POST /ap4m/settle
  - GET  /ap4m/settlements/{request_id}
  - POST /agent-pay/v1/tokens/issue
  - POST /agent-pay/v1/authorize
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from models import Mandate, PurchaseRequest, Settlement

router = APIRouter(prefix="/ap4m", tags=["mock-ap4m"])
agent_pay_router = APIRouter(prefix="/agent-pay/v1", tags=["Mastercard Agent Pay Mock"])

# In-memory settlement store (stand-in for guaranteed settlement ledger)
settlements: dict[str, Settlement] = {}

# In-memory MDES token vault for simulation
TOKEN_VAULT: dict[str, dict] = {}


# ────────────────────────────────────────────────────────────────────
# Screen — pretend credentialing + permissioning (Product.md)
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
    Credentialing + Permissioning check:
    - Agent id must start with 'agent_' (credential check).
    - Amount must be <= mandate.max_amount and category must be in allowed_categories.
    """
    if not purchase.agent_id.startswith("agent_"):
        return ScreenResult(
            credentialed=False,
            permitted=False,
            reason=f"Agent '{purchase.agent_id}' is not credentialed (must start with 'agent_').",
        )

    if purchase.amount > mandate.max_amount:
        return ScreenResult(
            credentialed=True,
            permitted=False,
            reason=f"Amount ${purchase.amount:.2f} exceeds mandate max ${mandate.max_amount:.2f}.",
        )

    if purchase.category not in mandate.allowed_categories:
        return ScreenResult(
            credentialed=True,
            permitted=False,
            reason=f"Category '{purchase.category}' is not allowed under mandate {mandate.allowed_categories}.",
        )

    return ScreenResult(credentialed=True, permitted=True, reason="Agent credentialed and purchase in mandate.")


@router.post("/screen", response_model=ScreenResult)
async def screen_endpoint(body: _ScreenIn):
    return screen(body.purchase, body.mandate)


# ────────────────────────────────────────────────────────────────────
# Settle — called only after gateway says auto_approve (Product.md)
# ────────────────────────────────────────────────────────────────────

class _SettleIn(BaseModel):
    request_id: str
    amount: float
    route: str  # the gateway's routing decision


def settle(request_id: str, amount: float, route: str) -> Settlement:
    """
    Settlement logic:
    - If route != 'auto_approve' -> status 'refused'
    - amount >= 100              -> status 'escrow' (held until delivery is confirmed)
    - amount < 100               -> status 'clawback_window' (settled instantly, reversible)
    """
    if route != "auto_approve":
        s = Settlement(
            request_id=request_id,
            status="refused",
            amount=amount,
            note="Gateway did not auto-approve; payment refused.",
        )
    elif amount >= 100.0:
        s = Settlement(
            request_id=request_id,
            status="escrow",
            amount=amount,
            note="Held in escrow until delivery is confirmed.",
        )
    else:
        s = Settlement(
            request_id=request_id,
            status="clawback_window",
            amount=amount,
            note="Settled instantly, reversible within 10-minute clawback window.",
        )

    settlements[request_id] = s
    return s


@router.post("/settle", response_model=Settlement)
async def settle_endpoint(body: _SettleIn):
    return settle(body.request_id, body.amount, body.route)


@router.get("/settlements/{request_id}", response_model=Settlement)
async def get_settlement(request_id: str):
    if request_id not in settlements:
        raise HTTPException(404, "Settlement not found")
    return settlements[request_id]


# ────────────────────────────────────────────────────────────────────
# MDES Agentic Token Mock (Kelvin's deeper mock)
# ────────────────────────────────────────────────────────────────────

class TokenEnrollmentRequest(BaseModel):
    customer_id: str
    card_last4: str
    agent_id: str
    max_amount_per_txn: float
    allowed_mccs: list[str]
    expires_in_days: int = 30


class AgentPayCheckoutRequest(BaseModel):
    agentic_token: str
    merchant_id: str
    merchant_category: str
    amount: float
    currency: str
    confirmation_id: str


@agent_pay_router.post("/tokens/issue")
async def issue_agentic_token(req: TokenEnrollmentRequest):
    """Mints a simulated MDES Agentic Token bound to specific agent policies."""
    token = f"tok_agent_{uuid.uuid4().hex[:16]}"
    record = {
        "agentic_token": token,
        "customer_id": req.customer_id,
        "agent_id": req.agent_id,
        "card_last4": req.card_last4,
        "max_amount": req.max_amount_per_txn,
        "allowed_mccs": req.allowed_mccs,
        "status": "ACTIVE",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    TOKEN_VAULT[token] = record
    return {"status": "success", "agentic_token": token, "policy_bound": record}


@agent_pay_router.post("/authorize")
async def authorize_transaction(req: AgentPayCheckoutRequest):
    """Simulates Mastercard network authorization verifying the Agentic Token and policy."""
    token_record = TOKEN_VAULT.get(req.agentic_token)
    if not token_record:
        raise HTTPException(401, "Invalid or unrecognized Agentic Token.")

    if token_record["status"] != "ACTIVE":
        raise HTTPException(403, "Agentic Token is suspended or revoked.")

    if req.amount > token_record["max_amount"]:
        raise HTTPException(
            400,
            f"Authorization declined: Amount exceeds agent mandate limit (${token_record['max_amount']}).",
        )

    if req.merchant_category not in token_record["allowed_mccs"]:
        raise HTTPException(
            400,
            f"Authorization declined: Merchant category {req.merchant_category} not allowed under mandate.",
        )

    auth_code = f"MC-{uuid.uuid4().hex[:8].upper()}"
    return {
        "status": "APPROVED",
        "authorization_code": auth_code,
        "network": "Mastercard Agent Pay",
        "cleared_amount": req.amount,
        "currency": req.currency,
        "settled_at": datetime.now(timezone.utc).isoformat(),
        "token_ref": req.agentic_token[:10] + "...",
    }
