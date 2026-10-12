"""
models.py
Shared Pydantic v2 data shapes for the Judgment and Accountability Layer.

Everyone imports from here. DO NOT RENAME FIELDS — John resolves drift at merge time.
"""

from pydantic import BaseModel, Field


class Mandate(BaseModel):
    owner_id: str
    task: str                                   # what the owner actually asked for
    max_amount: float
    currency: str = "USD"
    allowed_categories: list[str]
    trusted_instruction_sources: list[str] = ["owner"]


class PurchaseRequest(BaseModel):
    request_id: str
    agent_id: str
    agent_developer_id: str
    seller_id: str
    seller_name: str
    amount: float
    currency: str = "USD"
    category: str
    justification: str                          # task, why this seller, alternatives considered
    instruction_source: str                     # "owner" | "webpage" | "email" | "chat"
    instruction_text: str


class CheckResult(BaseModel):
    check_name: str
    status: str                                 # "pass" | "flag" | "block"
    risk: int = Field(ge=0, le=100)
    reasons: list[str]


class DecisionReceipt(BaseModel):
    request_id: str
    mandate: Mandate
    purchase: PurchaseRequest
    checks: list[CheckResult]
    route: str                                  # "auto_approve" | "hold" | "block"
    liable_party: str                           # "none" | "seller" | "owner" | "verifier" | "agent_developer"
    liability_reason: str
    signature: str                              # hex hmac of the canonical json


class Settlement(BaseModel):
    request_id: str
    status: str                                 # "escrow" | "settled" | "clawback_window" | "refused"
    amount: float
    note: str


# ---------- Helper type used by Zuzu's risk-signals checker ----------

class PaymentHistoryEntry(BaseModel):
    """A single past payment, used by assess_risk() to detect patterns."""
    seller_id: str
    amount: float
    timestamp: str                              # ISO-8601 string
