"""
main.py
Unified application runner pointing to app.py.

Run:
    uvicorn main:app --reload --port 8000
    or
    python main.py
"""
from app import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)