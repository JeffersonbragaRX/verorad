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

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
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
    # SPA build ja gerado (npm run build). StaticFiles(html=True) so
    # serve index.html para a raiz e arquivos que realmente existem —
    # uma rota client-side como /biblioteca/12 nao e um arquivo, entao
    # cai em 404 sem o catch-all abaixo (bug real encontrado testando
    # recarregar a pagina numa rota interna). O catch-all so e atingido
    # quando nada mais bateu (rotas de API e arquivos estaticos tem
    # prioridade por serem registrados/montados antes).
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        # Uma rota /api/* que nao bateu em nenhum router acima e um
        # endpoint que nao existe — precisa continuar 404, nunca cair
        # silenciosamente no index.html (bug real: chamada de API
        # incorreta/removida devolvia 200 com HTML em vez de 404,
        # escondendo o erro em vez de sinaliza-lo).
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Endpoint não encontrado")
        candidate = FRONTEND_DIST / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
