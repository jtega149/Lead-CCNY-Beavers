"""
agent_pay_mock.py
Simulates Mastercard Agent Pay (MDES Agentic Tokens, policy binding, and authorization network).
Allows testing agent-initiated checkouts without needing live production Mastercard API keys.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/agent-pay/v1", tags=["Mastercard Agent Pay Mock"])

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

# In-memory token vault for demo
TOKEN_VAULT: dict[str, dict] = {}

@router.post("/tokens/issue")
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
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    TOKEN_VAULT[token] = record
    return {"status": "success", "agentic_token": token, "policy_bound": record}

@router.post("/authorize")
async def authorize_transaction(req: AgentPayCheckoutRequest):
    """Simulates Mastercard network authorization verifying the Agentic Token and policy."""
    token_record = TOKEN_VAULT.get(req.agentic_token)
    if not token_record:
        raise HTTPException(401, "Invalid or unrecognized Agentic Token.")
    
    if token_record["status"] != "ACTIVE":
        raise HTTPException(403, "Agentic Token is suspended or revoked.")

    # Policy validation checks
    if req.amount > token_record["max_amount"]:
        raise HTTPException(400, f"Authorization declined: Amount exceeds agent mandate limit (${token_record['max_amount']}).")
    
    if req.merchant_category not in token_record["allowed_mccs"]:
        raise HTTPException(400, f"Authorization declined: Merchant category {req.merchant_category} not allowed under mandate.")

    # Generate successful settlement receipt
    auth_code = f"MC-{uuid.uuid4().hex[:8].upper()}"
    return {
        "status": "APPROVED",
        "authorization_code": auth_code,
        "network": "Mastercard Agent Pay",
        "cleared_amount": req.amount,
        "currency": req.currency,
        "settled_at": datetime.now(timezone.utc).isoformat(),
        "token_ref": req.agentic_token[:10] + "..."
    }