"""
disputes_api.py
Customer-facing endpoints: view flagged transactions, submit complaints/disputes, and route
chargebacks to the right party using explicit, auditable rules.

Run:  uvicorn disputes_api:app --reload

Design notes:
  * Customers never see the raw risk score or the label "friendly fraud". They see a neutral
    "unusual activity, please review" status. (Avoids accusing customers and avoids teaching
    bad actors how to game the model.)
  * In card networks, chargebacks are filed by the ISSUER. This API creates the dispute case and
    routes it; the issuer integration performs the actual chargeback. (ASSUMPTION, see README)
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Customer Disputes API")

# ------------------------------ models -------------------------------------


class Reason(str, Enum):
    UNAUTHORIZED = "unauthorized"                  # "I never approved this"
    AGENT_EXCEEDED_MANDATE = "agent_exceeded_mandate"
    NOT_RECEIVED = "not_received"
    NOT_AS_DESCRIBED = "not_as_described"
    DUPLICATE = "duplicate"
    INCORRECT_AMOUNT = "incorrect_amount"
    OTHER = "other"


class Party(str, Enum):
    ISSUER = "issuer"
    MERCHANT = "merchant"
    MASTERCARD = "mastercard"
    AGENT_PROVIDER = "agent_provider"


class DisputeIn(BaseModel):
    txn_id: str
    reason: Reason
    description: str = Field(..., min_length=10, max_length=4000)
    attachment_ids: list[str] = []


@dataclass
class RoutingDecision:
    primary: Party
    notify: list[Party] = field(default_factory=list)
    merchant_first_window_days: int = 0     # >0: try merchant resolution before issuer chargeback
    attach_evidence_packet: bool = False
    priority: str = "normal"                # normal | review
    actions: list[str] = field(default_factory=list)
    rule_id: str = ""


# ------------------------------ routing rules ------------------------------


def route_dispute(reason: Reason, txn: dict, fraud: dict, confirmation: Optional[dict]) -> RoutingDecision:
    """
    txn: transaction record, fraud: FraudResult as dict, confirmation: stored confirmation evidence or None.
    Rules are ordered; first match wins. Keep them in config/Cosmos so compliance can review changes.
    """
    flagged = fraud.get("friendly_fraud_flag", False)

    # R1: Customer says unauthorized, but we hold a hash-bound confirmation + model flags it.
    #     Still goes to the issuer (customer rights are preserved) with evidence and human review.
    if reason == Reason.UNAUTHORIZED and confirmation and flagged:
        return RoutingDecision(Party.ISSUER, [Party.MASTERCARD], attach_evidence_packet=True,
                               priority="review", rule_id="R1",
                               actions=["Attach confirmation record + mandate", "Queue for analyst review"])

    # R2: Unauthorized and NO confirmation on file -> treat as true fraud / possible agent compromise.
    if reason == Reason.UNAUTHORIZED:
        return RoutingDecision(Party.ISSUER, [Party.MASTERCARD, Party.AGENT_PROVIDER], priority="review",
                               rule_id="R2",
                               actions=["Suspend agent token", "Open compromise investigation"])

    # R3: Agent acted outside the customer's mandate -> issuer, and the agent provider is accountable.
    if reason == Reason.AGENT_EXCEEDED_MANDATE:
        return RoutingDecision(Party.ISSUER, [Party.AGENT_PROVIDER, Party.MASTERCARD],
                               attach_evidence_packet=True, rule_id="R3",
                               actions=["Revoke or limit agent mandate", "Notify agent provider"])

    # R4: Merchant-performance problems -> merchant first, escalate to issuer if unresolved.
    if reason in (Reason.NOT_RECEIVED, Reason.NOT_AS_DESCRIBED, Reason.DUPLICATE, Reason.INCORRECT_AMOUNT):
        return RoutingDecision(Party.MERCHANT, [Party.ISSUER], merchant_first_window_days=10,
                               attach_evidence_packet=True, rule_id="R4",
                               actions=["Send case to merchant", "Auto-escalate to issuer after window"])

    # R5: Everything else -> issuer triage.
    return RoutingDecision(Party.ISSUER, rule_id="R5", actions=["Manual triage"])


# ------------------------------ integrations -------------------------------


async def current_customer(authorization: str = Header(...)) -> str:
    """TODO: validate Entra External ID JWT; return customer id."""
    raise NotImplementedError


class Repo:
    """Cosmos DB access. Dispute cases are partitioned by customer_id; Purview labels PII fields."""
    def flagged_transactions(self, customer_id: str) -> list[dict]: raise NotImplementedError
    def transaction(self, txn_id: str) -> Optional[dict]: raise NotImplementedError
    def fraud_result(self, txn_id: str) -> dict: raise NotImplementedError
    def confirmation_for(self, txn_id: str) -> Optional[dict]: raise NotImplementedError
    def find_by_idempotency(self, customer_id: str, key: str) -> Optional[dict]: raise NotImplementedError
    def save_dispute(self, d: dict) -> None: raise NotImplementedError
    def get_dispute(self, customer_id: str, dispute_id: str) -> Optional[dict]: raise NotImplementedError


repo = Repo()


def publish_event(event_type: str, data: dict) -> None:
    """TODO: Event Grid -> (a) issuer/merchant connectors, (b) Sentinel, (c) Power BI dataset."""
    raise NotImplementedError


# ------------------------------ endpoints ----------------------------------


def to_customer_view(txn: dict, fraud: dict) -> dict:
    """Strip model internals. Customers see a neutral status and a suggested action."""
    return {
        "txn_id": txn["txn_id"], "merchant": txn["merchant_name"], "amount": txn["amount"],
        "currency": txn["currency"], "date": txn["timestamp"],
        "status": "Unusual activity: please review",
        "can_dispute": True,
    }


@app.get("/transactions/flagged")
async def list_flagged(customer_id: str = Depends(current_customer)):
    txns = repo.flagged_transactions(customer_id)
    return [to_customer_view(t, repo.fraud_result(t["txn_id"])) for t in txns]


@app.post("/disputes", status_code=201)
async def submit_dispute(body: DisputeIn, customer_id: str = Depends(current_customer),
                         idempotency_key: str = Header(...)):
    existing = repo.find_by_idempotency(customer_id, idempotency_key)
    if existing:
        return existing

    txn = repo.transaction(body.txn_id)
    if not txn or txn["customer_id"] != customer_id:       # object-level authorization
        raise HTTPException(404, "Transaction not found")

    fraud = repo.fraud_result(body.txn_id)
    confirmation = repo.confirmation_for(body.txn_id)
    decision = route_dispute(body.reason, txn, fraud, confirmation)

    dispute = {
        "id": str(uuid.uuid4()), "customer_id": customer_id, "idempotency_key": idempotency_key,
        "txn_id": body.txn_id, "reason": body.reason.value, "description": body.description,
        "attachment_ids": body.attachment_ids, "status": "ROUTED",
        "routing": {"primary": decision.primary.value, "notify": [p.value for p in decision.notify],
                    "merchant_first_window_days": decision.merchant_first_window_days,
                    "priority": decision.priority, "rule_id": decision.rule_id,
                    "actions": decision.actions},
        "evidence_packet": ({"confirmation": confirmation, "fraud_signals": fraud.get("reasons")}
                            if decision.attach_evidence_packet else None),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    repo.save_dispute(dispute)
    publish_event("Guardian.DisputeCreated", {"dispute_id": dispute["id"], "routing": dispute["routing"]})

    # The customer sees where the case went and what happens next, not the internal rule or score.
    return {"dispute_id": dispute["id"], "status": dispute["status"],
            "being_reviewed_by": decision.primary.value,
            "next_step": ("The merchant has 10 days to respond before your bank steps in."
                          if decision.merchant_first_window_days else "Your bank will review this case.")}


@app.get("/disputes/{dispute_id}")
async def get_dispute(dispute_id: str, customer_id: str = Depends(current_customer)):
    d = repo.get_dispute(customer_id, dispute_id)
    if not d:
        raise HTTPException(404, "Dispute not found")
    return {k: d[k] for k in ("id", "txn_id", "reason", "status", "created_at")}
