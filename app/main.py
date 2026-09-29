from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.auth.router import router as auth_router
from app.api.business.router import router as business_router
from app.api.form16.router import router as form16_router


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Python FastAPI backend built for the iTaxEasy Mobile APK (Phase 1)",
    version="0.1.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth_router, prefix="/api/auth", tags=["Authentication"])
app.include_router(business_router, prefix="/api/business", tags=["Business"])
app.include_router(form16_router, prefix="/api/form16", tags=["Form 16"])


@app.get("/")
async def root():
    return {
        "status": "healthy",
        "project": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
        "docs_url": "/docs"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=3002, reload=True)
