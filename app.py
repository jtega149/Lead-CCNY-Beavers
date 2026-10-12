"""
app.py — Main FastAPI application
Mounts all team routers into a single unified server.

Run:
    uvicorn app:app --reload
"""

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

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
from sense_check import router as sense_router
from mock_ap4m import router as ap4m_router, agent_pay_router

app.include_router(gateway_router)
app.include_router(provenance_router)
app.include_router(verifier_router)
app.include_router(risk_signals_router)
app.include_router(receipts_router)
app.include_router(sense_router)
app.include_router(ap4m_router)
app.include_router(agent_pay_router)


# ── Frontend assets (index.html loads static/css and static/js) ─────
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


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
            "GET  /demo/scenarios     — demo.py payloads for the UI",
            "POST /judge              — full pipeline (John)",
            "POST /judge/{id}/decision — human approves / rejects a held payment",
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


@app.get("/demo/scenarios")
async def demo_scenarios():
    """The demo.py scenarios, so the frontend runs the same payloads as the CLI demo."""
    from demo import GOOD_PURCHASE, SIX_LAYOVERS, LIMIT_DODGING, NOT_DELIVERED, OFF_TASK_UPSELL, PROMPT_INJECTION
    return [
        {"key": "good", "label": "Good purchase", "expect": "auto_approve", "payload": GOOD_PURCHASE},
        {"key": "inject", "label": "Prompt injection", "expect": "block", "payload": PROMPT_INJECTION},
        {"key": "dodge", "label": "Limit-dodging scam", "expect": "block", "payload": LIMIT_DODGING},
        {"key": "undelivered", "label": "Paid, not delivered", "expect": "auto_approve · seller liable", "payload": NOT_DELIVERED},
        {"key": "layovers", "label": "6-layover flight", "expect": "hold · Azure sense check", "payload": SIX_LAYOVERS},
        {"key": "upsell", "label": "Off-task upsell", "expect": "block (Azure) · hold (rules only)", "payload": OFF_TASK_UPSELL},
    ]


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
