"""
main.py
Unified application runner mounting all trust layer services.

Run:
    uvicorn main:app --reload --port 8000
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

# Import routers from our modular service files
from disputes_api import app as disputes_app
from purchase_confirmation import app as confirmation_app
from agent_pay_mock import router as agent_pay_router

app = FastAPI(
    title="Agentic Trust Layer · Mastercard & Microsoft Cloud",
    description="Unified Guardian infrastructure for agent-initiated payments, friendly-fraud scoring, and dispute routing.",
    version="1.0.0"
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount individual service sub-applications or routers
app.mount("/api/disputes", disputes_app)
app.mount("/api/purchases", confirmation_app)
app.include_router(agent_pay_router)

@app.get("/")
async def serve_demo_ui():
    """Serves the interactive frontend prototype simulator."""
    return FileResponse("index.html")

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "services": ["disputes_api", "purchase_confirmation", "agent_pay_mock", "friendly_fraud_engine"],
        "cloud_environment": "Microsoft Azure / Mastercard Agent Pay Mock"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)