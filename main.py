from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import payroll

app = FastAPI(
    title="Payroll Analysis API",
    description="API for analyzing payroll data and flagging labor law violations",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(payroll.router)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Welcome to Payroll Analysis API",
        "docs": "/docs",
        "health": "/payroll/health"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)

