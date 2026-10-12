"""
app.py — Main FastAPI application
Mounts all team routers into a single unified server.

Run:
    uvicorn app:app --reload
"""

import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

app = FastAPI(
    title="Judgment & Accountability Layer · Mastercard & Azure Cloud",
    description="A trust layer between 'the agent decided to pay' and 'the money moved.'",
    version="1.0.0",
)

# ── Enable CORS for frontend integration ─────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Mount team routers ──────────────────────────────────────────────
from gateway import router as gateway_router
from provenance import router as provenance_router
from verifier import router as verifier_router
from risk_signals import router as risk_signals_router
from receipts import router as receipts_router
from mock_ap4m import router as ap4m_router, agent_pay_router

app.include_router(gateway_router)
app.include_router(provenance_router)
app.include_router(verifier_router)
app.include_router(risk_signals_router)
app.include_router(receipts_router)
app.include_router(ap4m_router)
app.include_router(agent_pay_router)


# ── Frontend & Health Endpoints ─────────────────────────────────────
@app.get("/")
async def root(request: Request):
    """Serves the interactive frontend prototype if requested by browser, otherwise API status."""
    accept = request.headers.get("accept", "")
    if "text/html" in accept and os.path.exists("index.html"):
        return FileResponse("index.html")
    return {
        "service": "Judgment & Accountability Layer",
        "status": "running",
        "ui": "/ui",
        "docs": "/docs",
        "routes": [
            "POST /judge              — full pipeline (John)",
            "POST /provenance         — instruction source check (Aditya)",
            "POST /verify             — mandate match check (Taamim)",
            "POST /risk               — seller & pattern check (Zuzu)",
            "POST /receipts           — decision receipt (Axyl)",
            "POST /ap4m/screen        — mock credentialing (Kelvin)",
            "POST /ap4m/settle        — mock settlement (Kelvin)",
            "POST /agent-pay/v1/tokens/issue  — MDES token minting (Kelvin)",
            "POST /agent-pay/v1/authorize     — card network auth (Kelvin)",
        ],
    }


@app.get("/ui")
async def serve_demo_ui():
    """Explicit endpoint to view interactive simulator."""
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return JSONResponse(status_code=404, content={"error": "index.html not found"})


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "services": [
            "gateway",
            "provenance",
            "verifier",
            "risk_signals",
            "receipts",
            "mock_ap4m",
        ],
        "cloud_environment": "Microsoft Azure / Mastercard Agent Pay Mock",
    }
