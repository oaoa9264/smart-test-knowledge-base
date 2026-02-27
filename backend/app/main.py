import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.architecture import BACKEND_DIR, router as architecture_router
from app.api.ai_parse import router as ai_router
from app.api.coverage import router as coverage_router
from app.api.projects import router as project_router
from app.api.recommendation import router as recommendation_router
from app.api.rules import router as rule_router
from app.api.testcases import router as testcase_router
from app.core.database import engine
from app.models.entities import Base

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Test Knowledge Base MVP", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


os.makedirs(os.path.join(BACKEND_DIR, "uploads"), exist_ok=True)
app.mount("/uploads", StaticFiles(directory=os.path.join(BACKEND_DIR, "uploads")), name="uploads")

app.include_router(project_router)
app.include_router(rule_router)
app.include_router(testcase_router)
app.include_router(coverage_router)
app.include_router(recommendation_router)
app.include_router(ai_router)
app.include_router(architecture_router)
