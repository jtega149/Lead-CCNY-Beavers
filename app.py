"""
app.py — Main FastAPI application
Mounts all team routers into a single server.

Run:
    uvicorn app:app --reload
"""

from fastapi import FastAPI

app = FastAPI(
    title="Judgment & Accountability Layer",
    description="A layer between 'the agent decided to pay' and 'the money moved.'",
    version="0.1.0",
)

# ── Mount team routers ──────────────────────────────────────────────

from gateway import router as gateway_router
from provenance import router as provenance_router
from verifier import router as verifier_router
from risk_signals import router as risk_signals_router
from receipts import router as receipts_router
from mock_ap4m import router as ap4m_router

app.include_router(gateway_router)
app.include_router(provenance_router)
app.include_router(verifier_router)
app.include_router(risk_signals_router)
app.include_router(receipts_router)
app.include_router(ap4m_router)


@app.get("/")
async def root():
    return {
        "service": "Judgment & Accountability Layer",
        "status": "running",
        "routes": [
            "POST /judge        — full pipeline (John)",
            "POST /provenance   — instruction source check (Aditya)",
            "POST /verify       — mandate match check (Taamim)",
            "POST /risk         — seller & pattern check (Zuzu)",
            "POST /receipts     — decision receipt (Axyl)",
            "POST /ap4m/screen  — mock credentialing (Kelvin)",
            "POST /ap4m/settle  — mock settlement (Kelvin)",
        ],
    }
