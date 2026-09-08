#!/usr/bin/env bash
# LaudoCore — inicia o app completo (API + interface) com um comando.
#
# Pre-requisito (uma vez, antes da primeira execucao): o corpus real
# ingerido e processado —
#   python3 scripts/ingest_vertical.py
#   python3 scripts/extract_concepts.py
#
# Uso:
#   ./run.sh
# Depois abra http://localhost:8000 no navegador.

set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f "data/processed/laudocore.db" ]; then
  echo "data/processed/laudocore.db não existe."
  echo "Rode antes: python3 scripts/ingest_vertical.py && python3 scripts/extract_concepts.py"
  exit 1
fi

if ! python3 -c "import fastapi, uvicorn" >/dev/null 2>&1; then
  echo "Instalando dependências Python (requirements.txt)…"
  pip3 install -r requirements.txt
fi

if [ ! -d "frontend/node_modules" ]; then
  echo "Instalando dependências do frontend (primeira execução)…"
  (cd frontend && npm install)
fi

echo "Construindo a interface…"
(cd frontend && npm run build)

echo "Subindo o LaudoCore em http://localhost:8000"
python3 -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8000
