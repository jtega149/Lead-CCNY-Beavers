"""
friendly_fraud.py
Scores agent-initiated transactions for "friendly fraud" risk, i.e. purchases that are
uncharacteristic for the customer and therefore likely to be disputed later even though
the customer's agent was authorized to make them.

Deployed as an Azure Function (Event Grid trigger) and also imported by the
confirmation service (pre-authorization scoring).

NOTE: Rule-based heuristics below are a transparent v1 baseline. Replace `score_transaction`
internals with a model trained on labeled dispute outcomes (Azure AI Foundry / Azure ML)
once data exists, and keep the rule output as features + explanations.
"""
from __future__ import annotations

import json
import logging
import statistics
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional

# ----------------------------- data models ---------------------------------


@dataclass
class AgentTransaction:
    txn_id: str
    customer_id: str
    agent_id: str
    merchant_id: str
    merchant_category: str            # MCC
    amount: float
    currency: str
    country: str
    timestamp: datetime
    mandate_id: Optional[str] = None  # the customer's documented constraints for the agent
    mandate_max_amount: Optional[float] = None
    mandate_categories: list[str] = field(default_factory=list)
    confirmation_id: Optional[str] = None   # set when customer explicitly confirmed
    ship_to_changed: bool = False
    agent_txn_count_last_hour: int = 0


@dataclass
class CustomerProfile:
    customer_id: str
    amounts: list[float]                    # historical txn amounts
    merchant_ids: set[str]
    category_counts: dict[str, int]         # MCC -> count
    home_countries: set[str]
    active_hours_utc: set[int]              # hours with normal activity
    disputes_90d: int = 0

    @property
    def total_txns(self) -> int:
        return sum(self.category_counts.values())


@dataclass
class FraudResult:
    txn_id: str
    risk_score: int                    # 0-100, how uncharacteristic + dispute-prone
    friendly_fraud_likelihood: float   # 0-1
    friendly_fraud_flag: bool
    label: str                         # friendly_fraud_likely | agent_error_or_compromise | normal
    reasons: list[str]
    scored_at: str
    model_version: str = "rules-v1"


# ----------------------------- scoring logic -------------------------------

FLAG_THRESHOLD = 0.60
BEHAVIOR_WEIGHTS = {
    "amount": 0.30,
    "merchant": 0.15,
    "category": 0.15,
    "geo": 0.10,
    "time": 0.05,
    "ship_to": 0.10,
    "velocity": 0.05,
    "dispute_history": 0.10,
}


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def _amount_signal(amount: float, history: list[float]) -> tuple[float, str]:
    if len(history) < 5:
        return 0.3, "Limited purchase history; amount cannot be benchmarked reliably"
    med = statistics.median(history)
    mad = statistics.median([abs(a - med) for a in history]) or max(med * 0.1, 1.0)
    z = (amount - med) / (1.4826 * mad)          # robust z-score
    sig = _clamp((z - 2) / 4)
    reason = f"Amount {amount:.2f} is {z:.1f} robust std-devs above customer's median {med:.2f}"
    return sig, reason if sig > 0 else ""


def score_transaction(txn: AgentTransaction, profile: CustomerProfile) -> FraudResult:
    reasons: list[str] = []
    s: dict[str, float] = {}

    s["amount"], r = _amount_signal(txn.amount, profile.amounts)
    if r:
        reasons.append(r)

    s["merchant"] = 0.0 if txn.merchant_id in profile.merchant_ids else 1.0
    if s["merchant"]:
        reasons.append("First purchase from this merchant")

    share = profile.category_counts.get(txn.merchant_category, 0) / max(profile.total_txns, 1)
    s["category"] = _clamp(1 - share * 10)       # <10% share starts counting as rare
    if s["category"] > 0.5:
        reasons.append(f"Merchant category {txn.merchant_category} is rare for this customer")

    s["geo"] = 0.0 if txn.country in profile.home_countries else 1.0
    if s["geo"]:
        reasons.append(f"Merchant country {txn.country} outside customer's usual countries")

    s["time"] = 0.0 if txn.timestamp.astimezone(timezone.utc).hour in profile.active_hours_utc else 0.5
    s["ship_to"] = 1.0 if txn.ship_to_changed else 0.0
    if s["ship_to"]:
        reasons.append("Delivery destination differs from customer's saved addresses")

    s["velocity"] = _clamp((txn.agent_txn_count_last_hour - 2) / 5)
    if s["velocity"] > 0.4:
        reasons.append(f"Agent made {txn.agent_txn_count_last_hour} purchases in the last hour")

    s["dispute_history"] = _clamp(profile.disputes_90d / 3)
    if s["dispute_history"] > 0:
        reasons.append(f"{profile.disputes_90d} disputes in the last 90 days")

    behavior = sum(BEHAVIOR_WEIGHTS[k] * v for k, v in s.items())

    # Scope violations: the agent acted outside what the customer documented.
    scope_violation = (
        txn.mandate_id is None
        or (txn.mandate_max_amount is not None and txn.amount > txn.mandate_max_amount)
        or (txn.mandate_categories and txn.merchant_category not in txn.mandate_categories)
    )
    if scope_violation:
        reasons.append("Purchase falls outside the customer's documented agent mandate")

    has_confirmation = txn.confirmation_id is not None

    # Interpretation (assumption, see README): an uncharacteristic purchase that the customer
    # DID authorize (in-scope and/or explicitly confirmed) is the friendly-fraud pattern.
    # An uncharacteristic purchase OUTSIDE the mandate is more likely genuine agent error or
    # compromise, and should be routed as true fraud, not friendly fraud.
    likelihood = behavior * (1.0 if has_confirmation else 0.85)
    if scope_violation:
        likelihood *= 0.4

    if scope_violation and behavior >= 0.3:
        label = "agent_error_or_compromise"
    elif likelihood >= FLAG_THRESHOLD * 0.5 and behavior >= 0.35:
        label = "friendly_fraud_likely"
    else:
        label = "normal"

    flag = likelihood >= FLAG_THRESHOLD * 0.5 and behavior >= 0.35 and not scope_violation
    risk_score = round(100 * max(behavior, 0.9 if scope_violation and behavior >= 0.3 else 0))

    return FraudResult(
        txn_id=txn.txn_id,
        risk_score=risk_score,
        friendly_fraud_likelihood=round(_clamp(likelihood), 3),
        friendly_fraud_flag=flag,
        label=label,
        reasons=[x for x in reasons if x],
        scored_at=datetime.now(timezone.utc).isoformat(),
    )


# ----------------------- optional LLM explanation --------------------------


def explain_for_analyst(result: FraudResult) -> str:
    """Plain-language case summary for issuer/Mastercard analysts (never shown raw to customers)."""
    from openai import AzureOpenAI  # pip install openai

    client = AzureOpenAI(
        azure_endpoint="https://<your-resource>.openai.azure.com",
        api_version="2024-10-21",
        azure_ad_token_provider=_token_provider(),   # Entra managed identity, no API keys
    )
    resp = client.chat.completions.create(
        model="gpt-4o",  # your deployment name
        messages=[
            {"role": "system", "content": "Summarize fraud-model findings for a dispute analyst in 3 sentences. "
                                          "Do not invent facts beyond the provided signals."},
            {"role": "user", "content": json.dumps(asdict(result))},
        ],
    )
    return resp.choices[0].message.content


def _token_provider():
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider
    return get_bearer_token_provider(DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default")


# ---------------------- Azure Function (Event Grid) ------------------------

try:
    import azure.functions as func

    app = func.FunctionApp()

    @app.event_grid_trigger(arg_name="event")
    def score_agent_transaction(event: func.EventGridEvent):
        """Fires on `AgentPay.TransactionAuthorized`; writes result and emits `Guardian.TransactionScored`."""
        data = event.get_json()
        txn = AgentTransaction(**{**data, "timestamp": datetime.fromisoformat(data["timestamp"])})
        profile = load_profile(txn.customer_id)
        result = score_transaction(txn, profile)
        save_result(result)                 # Cosmos DB (partition key: customer_id)
        publish_scored_event(result)        # Event Grid topic -> Sentinel, Power BI feed, dispute service
        logging.info("scored txn=%s score=%s flag=%s", txn.txn_id, result.risk_score, result.friendly_fraud_flag)

except ImportError:  # allows importing scoring logic without the Functions runtime
    pass


def load_profile(customer_id: str) -> CustomerProfile:
    """TODO: query Cosmos DB / feature store. Identity attributes come via Entra External ID claims."""
    raise NotImplementedError


def save_result(result: FraudResult) -> None:
    """TODO: upsert into Cosmos DB container `fraud_results`."""
    raise NotImplementedError


def publish_scored_event(result: FraudResult) -> None:
    """TODO: azure.eventgrid.EventGridPublisherClient.send(...)"""
    raise NotImplementedError
