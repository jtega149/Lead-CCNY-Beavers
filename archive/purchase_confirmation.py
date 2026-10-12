"""
purchase_confirmation.py
Two-step flow: the agent PROPOSES a purchase (immutable summary), the customer CONFIRMS it,
and only then does the agent EXECUTE through Mastercard Agent Pay.

Key properties:
  * The agent cannot execute without a confirmation record bound to the exact proposal hash.
  * Price drift or expiry forces a re-proposal instead of silently charging a different amount.
  * Risky purchases require step-up authentication.
  * The confirmation record doubles as dispute evidence (agent intent, scope, authorization).

Run:  uvicorn purchase_confirmation:app --reload
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from friendly_fraud import AgentTransaction, score_transaction

app = FastAPI(title="Agent Purchase Confirmation Service")

PROPOSAL_TTL = timedelta(minutes=15)
PRICE_DRIFT_TOLERANCE = 0.01          # 1%
STEP_UP_AMOUNT = 500.00               # assumption: configurable per issuer policy

# ------------------------------ models -------------------------------------


class PurchaseRequest(BaseModel):
    utterance: str = Field(..., examples=["Buy plane tickets in December to LA under $600"])


class LineItem(BaseModel):
    description: str
    amount: float


class ProposalSummary(BaseModel):
    proposal_id: str
    merchant_name: str
    merchant_id: str
    merchant_category: str
    description: str                    # e.g. "AA 1234 SFO->LAX"
    route: Optional[str] = None
    schedule: Optional[str] = None
    base_price: float
    fees: list[LineItem]
    taxes: float
    total: float
    currency: str
    cancellation_policy: str
    constraints_applied: dict            # what the customer asked for (the mandate)
    expires_at: datetime
    proposal_hash: str
    prompt: str                          # human-readable confirmation text


class ConfirmRequest(BaseModel):
    proposal_id: str
    proposal_hash: str                   # must match what the customer was shown
    decision: str                        # "approve" | "decline"
    step_up_token: Optional[str] = None  # Entra step-up (MFA / passkey) proof


# ------------------------------ auth ---------------------------------------


async def current_customer(authorization: str = Header(...)) -> str:
    """TODO: validate the Entra External ID JWT (signature, audience, expiry); return customer id."""
    raise NotImplementedError


# --------------------------- stubs / integrations --------------------------


def parse_intent(utterance: str) -> dict:
    """Azure OpenAI structured-output call -> {"category","destination","month","max_total",...}.
    Reject anything the model could not extract with confidence; ask the customer instead."""
    raise NotImplementedError


def search_offers(constraints: dict) -> list[dict]:
    """Query merchants (airline/OTA APIs). Return offers with price breakdown."""
    raise NotImplementedError


def requote(offer_ref: str) -> float:
    """Re-fetch live total price for the offer before charging."""
    raise NotImplementedError


def verify_step_up(customer_id: str, token: Optional[str]) -> bool:
    """TODO: validate Entra step-up claim (acr/amr) is recent and belongs to this customer."""
    raise NotImplementedError


def agentpay_execute(*, customer_id: str, proposal: dict, confirmation_id: str) -> dict:
    """TODO: call Mastercard Agent Pay with the agentic token, mandate, and confirmation reference.
    Real request shape depends on Mastercard's partner API spec (ASSUMPTION)."""
    raise NotImplementedError


class Store:
    """Cosmos DB containers: `proposals` (TTL) and `confirmations` (append-only, Purview-labeled)."""
    def get_proposal(self, pid: str) -> Optional[dict]: raise NotImplementedError
    def put_proposal(self, p: dict) -> None: raise NotImplementedError
    def update_proposal(self, pid: str, **fields) -> None: raise NotImplementedError
    def append_confirmation(self, c: dict) -> None: raise NotImplementedError
    def profile(self, customer_id: str): raise NotImplementedError


store = Store()


def canonical_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


# ------------------------------ endpoints ----------------------------------


@app.post("/purchases/propose", response_model=ProposalSummary)
async def propose(req: PurchaseRequest, customer_id: str = Depends(current_customer)):
    constraints = parse_intent(req.utterance)
    offers = [o for o in search_offers(constraints) if o["total"] <= constraints["max_total"]]
    if not offers:
        raise HTTPException(404, "No offers found within your limits. Want to adjust the budget or dates?")
    offer = min(offers, key=lambda o: o["total"])      # v1: cheapest in-scope offer

    now = datetime.now(timezone.utc)
    body = {
        "customer_id": customer_id,
        "merchant_id": offer["merchant_id"],
        "merchant_name": offer["merchant_name"],
        "merchant_category": offer["mcc"],
        "description": offer["description"],
        "route": offer.get("route"),
        "schedule": offer.get("schedule"),
        "base_price": offer["base_price"],
        "fees": offer["fees"],
        "taxes": offer["taxes"],
        "total": offer["total"],
        "currency": offer["currency"],
        "cancellation_policy": offer["cancellation_policy"],
        "constraints_applied": constraints,
        "offer_ref": offer["offer_ref"],
    }
    pid = str(uuid.uuid4())
    expires = now + PROPOSAL_TTL
    phash = canonical_hash({**body, "proposal_id": pid, "expires_at": expires.isoformat()})

    fee_text = ", ".join(f"{f['description']} ${f['amount']:.2f}" for f in offer["fees"]) or "none"
    prompt = (
        f"I found: {offer['description']} on {offer['merchant_name']}"
        f"{' (' + offer['route'] + ')' if offer.get('route') else ''}, {offer.get('schedule', '')}.\n"
        f"Base ${offer['base_price']:.2f} + taxes ${offer['taxes']:.2f} + fees ({fee_text}) "
        f"= TOTAL ${offer['total']:.2f} {offer['currency']}.\n"
        f"Cancellation: {offer['cancellation_policy']}\n"
        f"Do you want me to purchase this? Nothing is charged until you confirm."
    )

    store.put_proposal({**body, "id": pid, "status": "PENDING", "expires_at": expires.isoformat(),
                        "proposal_hash": phash})
    return ProposalSummary(proposal_id=pid, expires_at=expires, proposal_hash=phash, prompt=prompt, **{
        k: body[k] for k in ("merchant_name", "merchant_id", "merchant_category", "description", "route",
                              "schedule", "base_price", "fees", "taxes", "total", "currency",
                              "cancellation_policy", "constraints_applied")})


@app.post("/purchases/confirm")
async def confirm(req: ConfirmRequest, request: Request, customer_id: str = Depends(current_customer)):
    p = store.get_proposal(req.proposal_id)
    if not p or p["customer_id"] != customer_id:
        raise HTTPException(404, "Proposal not found")
    if p["status"] != "PENDING":
        raise HTTPException(409, f"Proposal already {p['status']}")

    if req.decision == "decline":
        store.update_proposal(p["id"], status="DECLINED")
        return {"status": "declined"}

    now = datetime.now(timezone.utc)
    if now > datetime.fromisoformat(p["expires_at"]):
        store.update_proposal(p["id"], status="EXPIRED")
        raise HTTPException(410, "Proposal expired. Ask me to search again.")
    if req.proposal_hash != p["proposal_hash"]:
        raise HTTPException(409, "Confirmation does not match the proposal that was shown.")

    # Price drift: never charge more than what the customer saw.
    live_total = requote(p["offer_ref"])
    if live_total > p["total"] * (1 + PRICE_DRIFT_TOLERANCE):
        store.update_proposal(p["id"], status="SUPERSEDED")
        raise HTTPException(409, f"Price changed to ${live_total:.2f}. Please review a new proposal.")

    # Pre-authorization risk check (same model as post-auth scoring).
    txn = AgentTransaction(
        txn_id=f"pre-{p['id']}", customer_id=customer_id, agent_id="customer-agent",
        merchant_id=p["merchant_id"], merchant_category=p["merchant_category"], amount=p["total"],
        currency=p["currency"], country="US", timestamp=now, mandate_id=p["id"],
        mandate_max_amount=p["constraints_applied"].get("max_total"),
        mandate_categories=[p["merchant_category"]], confirmation_id="pending",
    )
    risk = score_transaction(txn, store.profile(customer_id))

    needs_step_up = p["total"] >= STEP_UP_AMOUNT or risk.friendly_fraud_flag
    if needs_step_up and not verify_step_up(customer_id, req.step_up_token):
        raise HTTPException(401, "Additional verification required for this purchase.",
                            headers={"X-Step-Up-Required": "true"})

    confirmation_id = str(uuid.uuid4())
    store.append_confirmation({      # immutable evidence record, used later by dispute intelligence
        "id": confirmation_id, "proposal_id": p["id"], "customer_id": customer_id,
        "proposal_hash": p["proposal_hash"], "confirmed_at": now.isoformat(),
        "ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"), "step_up_used": needs_step_up,
        "pre_auth_risk_score": risk.risk_score,
    })

    receipt = agentpay_execute(customer_id=customer_id, proposal=p, confirmation_id=confirmation_id)
    store.update_proposal(p["id"], status="EXECUTED", confirmation_id=confirmation_id)
    return {"status": "purchased", "confirmation_id": confirmation_id, "receipt": receipt}
