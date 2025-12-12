import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .routes import payroll

def setup_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    # Quiet overly-chatty loggers if needed
    logging.getLogger("uvicorn.access").setLevel(os.getenv("UVICORN_ACCESS_LOG_LEVEL", "INFO").upper())

setup_logging()
logger = logging.getLogger("payroll_api")

app = FastAPI(
    title="Payroll Analysis API",
    description="API + UI for analyzing payroll data and flagging labor law violations",
    version="1.1.0"
)

# Configure CORS (set ALLOWED_ORIGINS in Render, e.g. https://your-ui.onrender.com)
allowed_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
if not allowed_origins:
    allowed_origins = ["*"]  # OK for dev; set ALLOWED_ORIGINS for production

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,  # set to True only if you truly need cookies/auth
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(payroll.router)

# Static & UI
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

@app.get("/", response_class=HTMLResponse)
async def ui():
    """Serve the simple UI."""
    index_path = os.path.join(BASE_DIR, "templates", "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("payroll_api.main:app", host="0.0.0.0", port=8000, reload=True)
