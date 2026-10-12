"""
provenance.py  — Aditya
Instruction-provenance checker (prompt-injection detector).

Determines whether the "pay for this" instruction came from a trusted source
or from untrusted content the agent merely read.

Branch: aditya/provenance
Route:  POST /provenance
"""

from fastapi import APIRouter
from pydantic import BaseModel
from models import CheckResult, Mandate, PurchaseRequest

router = APIRouter(tags=["provenance"])


# ────────────────────────────────────────────────────────────────────
# Core function — this is what John imports
# ────────────────────────────────────────────────────────────────────

def check_provenance(purchase: PurchaseRequest, mandate: Mandate) -> CheckResult:
    """
    Checks the provenance of the purchase instruction (prompt-injection detection).

    Rules:
    1. instruction_source == "owner" AND in mandate.trusted_instruction_sources
       → pass, risk 5. Reason: Instruction came from the owner.
    2. instruction_source in {"webpage", "email", "chat"}
       → block, risk 95. Reason: Pay instruction came from untrusted content ({purchase.instruction_source}), which is the prompt-injection case.
    3. Any other source
       → flag, risk 50. Reason: Instruction source is unverified.

    Always echo purchase.instruction_text inside the reasons list.
    """
    source = purchase.instruction_source.strip().lower() if purchase.instruction_source else ""
    trusted = [s.strip().lower() for s in (mandate.trusted_instruction_sources or [])]

    if source == "owner" and source in trusted:
        status = "pass"
        risk = 5
        reason = "Instruction came from the owner."
    elif source in {"webpage", "email", "chat"}:
        status = "block"
        risk = 95
        reason = (
            f"Pay instruction came from untrusted content ({purchase.instruction_source}), "
            f"which is the prompt-injection case."
        )
    else:
        status = "flag"
        risk = 50
        reason = "Instruction source is unverified."

    reasons = [
        reason,
        f"Instruction text: {purchase.instruction_text}",
    ]

    return CheckResult(
        check_name="provenance",
        status=status,
        risk=risk,
        reasons=reasons,
    )


# ────────────────────────────────────────────────────────────────────
# Route — for standalone testing before the merge
# ────────────────────────────────────────────────────────────────────

class _ProvenanceIn(BaseModel):
    purchase: PurchaseRequest
    mandate: Mandate


@router.post("/provenance", response_model=CheckResult)
async def provenance_endpoint(body: _ProvenanceIn):
    """Standalone route: POST /provenance with {purchase, mandate}."""
    return check_provenance(body.purchase, body.mandate)
