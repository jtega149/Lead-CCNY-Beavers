"""
provenance.py  — Aditya
Instruction-provenance checker (prompt-injection detector).

Determines whether the "pay for this" instruction came from a trusted source
or from untrusted content the agent merely read.

Branch: aditya/provenance
Route:  POST /provenance
"""

from fastapi import APIRouter
from models import CheckResult, Mandate, PurchaseRequest

router = APIRouter(tags=["provenance"])


# ────────────────────────────────────────────────────────────────────
# Core function — this is what John imports
# ────────────────────────────────────────────────────────────────────

def check_provenance(purchase: PurchaseRequest, mandate: Mandate) -> CheckResult:
    """
    TODO: Implement the three rules from Product.md:

    1. instruction_source == "owner" AND in mandate.trusted_instruction_sources
       → pass, risk 5
    2. instruction_source in {"webpage", "email", "chat"}
       → block, risk 95
    3. anything else
       → flag, risk 50

    Always include purchase.instruction_text in the reasons list.
    """
    # STUB — replace with real logic
    return CheckResult(
        check_name="provenance",
        status="pass",
        risk=0,
        reasons=["stub — not yet implemented"],
    )


# ────────────────────────────────────────────────────────────────────
# Route — for standalone testing before the merge
# ────────────────────────────────────────────────────────────────────

from pydantic import BaseModel as _BM


class _ProvenanceIn(_BM):
    purchase: PurchaseRequest
    mandate: Mandate

@router.post("/provenance", response_model=CheckResult)
async def provenance_endpoint(body: _ProvenanceIn):
    """Standalone route: POST /provenance with {purchase, mandate}."""
    return check_provenance(body.purchase, body.mandate)
