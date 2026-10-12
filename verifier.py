"""
verifier.py  — Taamim
Independent purchase verifier.

Checks whether the agent's purchase justification actually matches
the owner's mandate. The agent never approves its own spending.

Branch: taamim/verifier
Route:  POST /verify
"""

import re
from fastapi import APIRouter
from pydantic import BaseModel

from models import CheckResult, Mandate, PurchaseRequest

router = APIRouter(tags=["verifier"])

# Common English stop words to exclude when identifying key words from task
STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can't", "cannot", "could", "couldn't",
    "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during",
    "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't",
    "have", "haven't", "having", "he", "her", "here", "hers", "herself", "him",
    "himself", "his", "how", "i", "if", "in", "into", "is", "isn't", "it", "its",
    "itself", "me", "more", "most", "mustn't", "my", "myself", "no", "nor", "not",
    "of", "off", "on", "once", "only", "or", "other", "ought", "our", "ours",
    "ourselves", "out", "over", "own", "same", "shan't", "she", "should", "shouldn't",
    "so", "some", "such", "than", "that", "the", "their", "theirs", "them",
    "themselves", "then", "there", "these", "they", "this", "those", "through",
    "to", "too", "under", "until", "up", "very", "was", "wasn't", "we", "were",
    "weren't", "what", "when", "where", "which", "while", "who", "whom", "why",
    "with", "won't", "would", "wouldn't", "you", "your", "yours", "yourself", "yourselves"
}


def _task_mentioned_in_justification(justification: str, task: str) -> bool:
    """
    Check if the justification references the mandate's task using
    case-insensitive substring check or key words from mandate.task.
    """
    if not justification or not task:
        return False

    task_clean = task.strip().lower()
    just_clean = justification.strip().lower()

    # 1. Full substring check
    if task_clean in just_clean:
        return True

    # 2. Key words matching
    task_tokens = re.findall(r"\b[a-z0-9]+\b", task_clean)
    just_tokens = set(re.findall(r"\b[a-z0-9]+\b", just_clean))

    # Meaningful keywords: exclude common stop words and pure numbers
    keywords = [
        token for token in task_tokens
        if token not in STOP_WORDS and not token.isdigit()
    ]

    if not keywords:
        keywords = task_tokens

    for kw in keywords:
        # Exact token match
        if kw in just_tokens:
            return True
        # Prefix/stem matching for words of length >= 4 (e.g. flight/flights, book/booked/booking)
        if len(kw) >= 4:
            for jw in just_tokens:
                if len(jw) >= 4 and (kw.startswith(jw) or jw.startswith(kw)):
                    return True

    return False


# ────────────────────────────────────────────────────────────────────
# Core function — this is what John imports
# ────────────────────────────────────────────────────────────────────

def verify_purchase(purchase: PurchaseRequest, mandate: Mandate) -> CheckResult:
    """
    Evaluate purchase against mandate rules from Product.md:

    1. purchase.amount > mandate.max_amount
       → block, risk 90
    2. purchase.category not in mandate.allowed_categories
       → block, risk 80
    3. justification does not mention task
       → flag, risk 60
    4. otherwise
       → pass, risk 10

    Always returns at least one human-readable reason in reasons.
    """
    # Rule 1: Amount exceeds mandate max_amount
    if purchase.amount > mandate.max_amount:
        return CheckResult(
            check_name="verifier",
            status="block",
            risk=90,
            reasons=[
                f"Amount ${purchase.amount:.2f} exceeds mandate max amount ${mandate.max_amount:.2f}."
            ],
        )

    # Rule 2: Category not allowed
    if purchase.category not in mandate.allowed_categories:
        return CheckResult(
            check_name="verifier",
            status="block",
            risk=80,
            reasons=[
                f"Category '{purchase.category}' is not in allowed categories {mandate.allowed_categories}."
            ],
        )

    # Rule 3: Justification does not reference the task
    if not _task_mentioned_in_justification(purchase.justification, mandate.task):
        return CheckResult(
            check_name="verifier",
            status="flag",
            risk=60,
            reasons=["Justification does not reference the mandate task."],
        )

    # Rule 4: All checks passed
    return CheckResult(
        check_name="verifier",
        status="pass",
        risk=10,
        reasons=["Purchase matches mandate task, category, and budget."],
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
