"""LaudoCore API — Fase 6/8. Serve os dados reais do vertical RM de
joelho (backend/*, data/processed/laudocore.db) para a interface.

Rodar (dev, so a API):
    uvicorn backend.api.app:app --reload --port 8000

Rodar servindo tambem o frontend ja construido (producao local):
    (a partir da raiz do projeto, com frontend/dist/ existente)
    uvicorn backend.api.app:app --port 8000
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.api.routers import reports, concepts, compile as compile_router, review_queue, stats

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = ROOT / "frontend" / "dist"

app = FastAPI(title="LaudoCore API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(reports.router)
app.include_router(concepts.router)
app.include_router(compile_router.router)
app.include_router(review_queue.router)
app.include_router(stats.router)


@app.exception_handler(FileNotFoundError)
def db_missing_handler(request: Request, exc: FileNotFoundError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/api/health")
def health():
    return {"status": "ok"}


if FRONTEND_DIST.exists():
    # SPA build ja gerado (npm run build) — serve estatico e cai em
    # index.html para qualquer rota que nao seja /api/*, permitindo
    # roteamento client-side (ver Fase 8/6).
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
